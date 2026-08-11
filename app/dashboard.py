r"""Streamlit interface for call analytics and coaching."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from src.copilot.providers import DeterministicProvider, LlamaCppServerProvider
from src.copilot.retrieval import PolicyRetriever
from src.copilot.service import CopilotService, local_api_key
from src.copilot.supervisor_agent import SupervisorAgentService
from src.knowledge.ingestion import KnowledgeIngestionError, KnowledgeIngestionService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KPI_ARTIFACT = PROJECT_ROOT / "dashboard" / "artifact.json"
SUPERVISOR_ARTIFACT = PROJECT_ROOT / "dashboard" / "supervisor_artifact.json"
SURVEY_ARTIFACT = PROJECT_ROOT / "dashboard" / "survey_representativeness_artifact.json"
MEMORY_ARTIFACT = PROJECT_ROOT / "dashboard" / "agent_memory_artifact.json"

STAGE_ORDER = ("start", "live", "end")
PRIORITY_ORDER = ("Needs attention", "Watch", "On track")
PRIORITY_COLORS = {
    "Needs attention": "#dc2626",
    "Watch": "#f59e0b",
    "On track": "#16a34a",
}

REQUIRED_KPI_DATASETS = {
    "kpi_summary",
    "aht_trend",
    "risk_trend",
    "behavior_rates",
    "kpi_status",
    "todays_focus",
    "call_highlights",
}
REQUIRED_SUPERVISOR_DATASETS = {
    "team_summary",
    "agent_overview",
    "priority_distribution",
    "team_behavior_coverage",
    "coaching_queue",
    "review_calls",
}
REQUIRED_SURVEY_DATASETS = {"agent_summary", "risk_mix", "surveyed_calls"}

COPILOT_MODES = {
    "Deterministic (no model required)": "deterministic",
    "Local Qwen LLM": "llama_cpp_server",
}


@st.cache_data(show_spinner=False)
def read_artifact(path_value: str, modified_time_ns: int) -> dict[str, Any]:
    """Read a JSON artifact; modified_time_ns invalidates Streamlit's cache."""

    del modified_time_ns
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def load_artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    missing_files = [
        str(path.relative_to(PROJECT_ROOT))
        for path in (KPI_ARTIFACT, SUPERVISOR_ARTIFACT, SURVEY_ARTIFACT)
        if not path.exists()
    ]
    if missing_files:
        raise FileNotFoundError(
            "Missing canonical dashboard artifact(s): " + ", ".join(missing_files)
        )

    kpi = read_artifact(str(KPI_ARTIFACT), KPI_ARTIFACT.stat().st_mtime_ns)
    supervisor = read_artifact(
        str(SUPERVISOR_ARTIFACT), SUPERVISOR_ARTIFACT.stat().st_mtime_ns
    )
    survey = read_artifact(str(SURVEY_ARTIFACT), SURVEY_ARTIFACT.stat().st_mtime_ns)
    _validate_datasets(kpi, REQUIRED_KPI_DATASETS, KPI_ARTIFACT)
    _validate_datasets(supervisor, REQUIRED_SUPERVISOR_DATASETS, SUPERVISOR_ARTIFACT)
    _validate_datasets(survey, REQUIRED_SURVEY_DATASETS, SURVEY_ARTIFACT)
    return kpi, supervisor, survey


@st.cache_resource(show_spinner=False)
def build_copilot_service(
    provider_name: str,
    artifact_modified_time_ns: int,
    survey_artifact_modified_time_ns: int,
    memory_artifact_modified_time_ns: int,
    config_modified_time_ns: int,
) -> CopilotService:
    """Create a Copilot service for the Streamlit session."""

    del (
        artifact_modified_time_ns,
        survey_artifact_modified_time_ns,
        memory_artifact_modified_time_ns,
        config_modified_time_ns,
    )
    if provider_name == "deterministic":
        return CopilotService(provider=DeterministicProvider())
    if provider_name == "llama_cpp_server":
        config_path = PROJECT_ROOT / "config" / "copilot_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        server = config["llama_cpp_server"]
        generation = config["generation"]
        provider = LlamaCppServerProvider(
            base_url=os.environ.get("COPILOT_BASE_URL", server["base_url"]),
            model=server["model"],
            temperature=generation["temperature"],
            max_tokens=generation["max_tokens"],
            timeout_sec=generation["timeout_sec"],
            api_key=local_api_key(),
        )
        return CopilotService(provider=provider)
    raise ValueError(f"Unsupported Copilot provider: {provider_name}")


@st.cache_resource(show_spinner=False)
def build_supervisor_agent_service(
    provider_name: str,
    supervisor_artifact_modified_time_ns: int,
    memory_artifact_modified_time_ns: int,
    config_modified_time_ns: int,
) -> SupervisorAgentService:
    """Create the bounded Supervisor Agent service for the Streamlit session."""

    del (
        supervisor_artifact_modified_time_ns,
        memory_artifact_modified_time_ns,
        config_modified_time_ns,
    )
    if provider_name == "deterministic":
        return SupervisorAgentService(provider=DeterministicProvider())
    if provider_name == "llama_cpp_server":
        config_path = PROJECT_ROOT / "config" / "copilot_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        server = config["llama_cpp_server"]
        generation = config["generation"]
        provider = LlamaCppServerProvider(
            base_url=os.environ.get("COPILOT_BASE_URL", server["base_url"]),
            model=server["model"],
            temperature=generation["temperature"],
            max_tokens=generation["max_tokens"],
            timeout_sec=generation["timeout_sec"],
            api_key=local_api_key(),
        )
        return SupervisorAgentService(provider=provider)
    raise ValueError(f"Unsupported Supervisor Agent provider: {provider_name}")


def _validate_datasets(
    artifact: dict[str, Any], required: set[str], artifact_path: Path
) -> None:
    datasets = artifact.get("snapshot", {}).get("datasets", {})
    missing = sorted(required - set(datasets))
    if missing:
        raise ValueError(
            f"{artifact_path.name} is missing required datasets: {', '.join(missing)}"
        )


def dataset_frames(artifact: dict[str, Any]) -> dict[str, pd.DataFrame]:
    return {
        name: pd.DataFrame(rows)
        for name, rows in artifact["snapshot"]["datasets"].items()
    }


def filter_frame(frame: pd.DataFrame, stage_id: str, agent_id: str | None = None) -> pd.DataFrame:
    result = frame.loc[frame["stage_id"] == stage_id].copy()
    if agent_id is not None and "agent_id" in result.columns:
        result = result.loc[result["agent_id"] == agent_id].copy()
    return result


def stage_labels(frame: pd.DataFrame) -> dict[str, str]:
    available = dict(zip(frame["stage_id"], frame["stage"]))
    return {stage: available[stage] for stage in STAGE_ORDER if stage in available}


def format_timestamp(value: Any) -> str:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        return str(value)
    return timestamp.strftime("%d %b %Y, %H:%M UTC")


def style_figure(figure: Any, *, percent_axis: bool = False) -> Any:
    figure.update_layout(
        template="plotly_white",
        margin=dict(l=20, r=20, t=55, b=20),
        legend_title_text="",
        hoverlabel=dict(namelength=-1),
    )
    if percent_axis:
        figure.update_yaxes(tickformat=".0%")
    return figure


def render_executive_overview(
    kpi_frames: dict[str, pd.DataFrame],
    supervisor_frames: dict[str, pd.DataFrame],
    stage_id: str,
) -> None:
    team = filter_frame(supervisor_frames["team_summary"], stage_id).iloc[0]
    st.header("Executive overview")
    st.caption(
        "A summary-first view of analyzed call evidence, team coaching priorities, "
        "and the boundaries that matter when interpreting the portfolio."
    )

    metric_columns = st.columns(5)
    metric_columns[0].metric("Calls reviewed", f"{int(team['calls_reviewed']):,}")
    metric_columns[1].metric("Agents in view", int(team["agents_in_view"]))
    metric_columns[2].metric(
        "Estimated AHT", f"{float(team['team_estimated_aht_sec']):,.0f} sec"
    )
    metric_columns[3].metric(
        "Heuristic risk proxy", f"{float(team['team_heuristic_risk']):.1f}"
    )
    metric_columns[4].metric(
        "Next-steps coverage", f"{float(team['next_steps_rate']):.0%}"
    )

    left, right = st.columns(2)
    priority = filter_frame(supervisor_frames["priority_distribution"], stage_id)
    priority["priority"] = pd.Categorical(
        priority["priority"], categories=PRIORITY_ORDER, ordered=True
    )
    priority = priority.sort_values("priority")
    priority_fig = px.bar(
        priority,
        x="priority",
        y="agent_count",
        color="priority",
        color_discrete_map=PRIORITY_COLORS,
        title="Team review priority",
        labels={"priority": "Review state", "agent_count": "Agents"},
    )
    priority_fig.update_layout(showlegend=False)
    left.plotly_chart(style_figure(priority_fig), width="stretch")

    behaviors = filter_frame(supervisor_frames["team_behavior_coverage"], stage_id)
    behavior_fig = px.bar(
        behaviors,
        x="behavior",
        y="value",
        color="series",
        barmode="group",
        title="Detected behaviors vs coaching benchmarks",
        labels={"behavior": "Behavior", "value": "Share of calls", "series": "Series"},
        color_discrete_sequence=["#2563eb", "#94a3b8"],
    )
    right.plotly_chart(style_figure(behavior_fig, percent_axis=True), width="stretch")

    queue = filter_frame(supervisor_frames["coaching_queue"], stage_id)
    queue = queue.sort_values(["priority_rank", "agent_id"]).head(5)
    st.subheader("Highest-priority coaching review")
    st.dataframe(
        queue[["agent_label", "priority", "focus_area", "why_now", "next_action"]],
        hide_index=True,
        width="stretch",
    )
    st.warning(
        "The risk value is an uncalibrated review proxy, not CSAT, QA, survey "
        "probability, or an official employee-performance score."
    )
    st.caption(f"Artifact freshness: {format_timestamp(team['freshness'])}")


def render_agent_tracker(
    kpi_frames: dict[str, pd.DataFrame], stage_id: str, agent_id: str
) -> None:
    summary = filter_frame(kpi_frames["kpi_summary"], stage_id, agent_id).iloc[0]
    focus = filter_frame(kpi_frames["todays_focus"], stage_id, agent_id).iloc[0]

    st.header("KPI Performance Tracker")
    st.caption(
        f"Evidence-backed coaching view for {summary['agent_label']}. "
        "Signals support review and coaching; they do not authorize employment decisions."
    )

    columns = st.columns(4)
    columns[0].metric("Calls considered", int(summary["calls_considered"]))
    columns[1].metric(
        "Estimated AHT",
        f"{float(summary['estimated_aht_sec']):,.0f} sec",
        f"Goal {float(summary['estimated_aht_goal_sec']):,.0f} sec",
        delta_color="off",
    )
    columns[2].metric(
        "Heuristic risk proxy",
        f"{float(summary['conversation_risk_score']):.1f}",
        f"Review threshold {float(summary['risk_rubric_threshold']):.0f}",
        delta_color="off",
    )
    columns[3].metric("Coaching focus", focus["focus_area"])

    st.subheader("Today's Focus")
    st.info(
        f"**Why:** {focus['why']}\n\n"
        f"**Recommended action:** {focus['recommended_action']}\n\n"
        f"**Guardrail:** {focus['guardrail']}"
    )

    left, right = st.columns(2)
    aht = filter_frame(kpi_frames["aht_trend"], stage_id, agent_id)
    aht_fig = px.line(
        aht,
        x="call_number",
        y="value",
        color="series",
        markers=True,
        title="Estimated AHT by analyzed call",
        labels={"call_number": "Call number", "value": "Seconds", "series": "Series"},
    )
    left.plotly_chart(style_figure(aht_fig), width="stretch")

    risk = filter_frame(kpi_frames["risk_trend"], stage_id, agent_id)
    risk_fig = px.line(
        risk,
        x="call_number",
        y="value",
        color="series",
        markers=True,
        title="Heuristic risk by analyzed call",
        labels={"call_number": "Call number", "value": "Proxy value", "series": "Series"},
    )
    right.plotly_chart(style_figure(risk_fig), width="stretch")

    behaviors = filter_frame(kpi_frames["behavior_rates"], stage_id, agent_id)
    behavior_fig = px.bar(
        behaviors,
        x="behavior",
        y="value",
        color="series",
        barmode="group",
        title="Detected service behaviors",
        labels={"behavior": "Behavior", "value": "Share of calls", "series": "Series"},
        color_discrete_sequence=["#2563eb", "#94a3b8"],
    )
    st.plotly_chart(style_figure(behavior_fig, percent_axis=True), width="stretch")

    status = filter_frame(kpi_frames["kpi_status"], stage_id, agent_id)
    st.subheader("Metric status and recommended actions")
    st.dataframe(
        status[
            [
                "metric",
                "current",
                "goal",
                "trend",
                "projection",
                "status",
                "recommended_action",
                "source_type",
            ]
        ],
        hide_index=True,
        width="stretch",
    )

    highlights = filter_frame(kpi_frames["call_highlights"], stage_id, agent_id)
    st.subheader("Calls selected for evidence review")
    st.dataframe(
        highlights[
            [
                "highlight",
                "call_id",
                "estimated_aht_sec",
                "heuristic_risk_score",
                "risk_level",
                "reason",
                "evidence",
            ]
        ],
        hide_index=True,
        width="stretch",
    )

    with st.expander("Synthetic portfolio KPI fixtures"):
        st.warning(
            "The values below demonstrate a future governed business-data integration. "
            "They are synthetic and must not be interpreted as observed outcomes."
        )
        synthetic_columns = st.columns(4)
        synthetic_columns[0].metric("CSAT demo", f"{float(summary['csat_demo']):.1%}")
        synthetic_columns[1].metric("QA demo", f"{float(summary['qa_demo']):.1%}")
        synthetic_columns[2].metric("NPS demo", f"{float(summary['nps_demo']):.1f}")
        synthetic_columns[3].metric(
            "Five Stars demo", f"{float(summary['five_star_demo']):.1%}"
        )


def render_supervisor_board(
    supervisor_frames: dict[str, pd.DataFrame], stage_id: str
) -> None:
    team = filter_frame(supervisor_frames["team_summary"], stage_id).iloc[0]
    overview = filter_frame(supervisor_frames["agent_overview"], stage_id)

    st.header("Supervisor Team Performance Board")
    st.caption(
        "Team triage for targeted human review, with transparent reasons and "
        "supporting call evidence."
    )

    columns = st.columns(5)
    columns[0].metric("Calls reviewed", int(team["calls_reviewed"]))
    columns[1].metric("Agents", int(team["agents_in_view"]))
    columns[2].metric("Needs attention", int(team["agents_needing_attention"]))
    columns[3].metric("Watch", int(team["agents_watch"]))
    columns[4].metric("Next-steps coverage", f"{float(team['next_steps_rate']):.0%}")

    scatter = px.scatter(
        overview,
        x="estimated_aht_sec",
        y="heuristic_risk_score",
        color="priority",
        hover_name="agent_label",
        hover_data=["focus_area", "priority_reason", "calls_reviewed"],
        color_discrete_map=PRIORITY_COLORS,
        category_orders={"priority": list(PRIORITY_ORDER)},
        title="Team review map: estimated AHT vs heuristic risk",
        labels={
            "estimated_aht_sec": "Estimated AHT (seconds)",
            "heuristic_risk_score": "Heuristic risk proxy",
            "priority": "Review state",
        },
    )
    scatter.add_vline(x=float(team["aht_goal_sec"]), line_dash="dash", line_color="#64748b")
    scatter.add_hline(y=float(team["risk_threshold"]), line_dash="dash", line_color="#64748b")
    st.plotly_chart(style_figure(scatter), width="stretch")

    left, right = st.columns(2)
    priority = filter_frame(supervisor_frames["priority_distribution"], stage_id)
    priority_fig = px.pie(
        priority,
        values="agent_count",
        names="priority",
        hole=0.55,
        color="priority",
        color_discrete_map=PRIORITY_COLORS,
        title="Review-state distribution",
        category_orders={"priority": list(PRIORITY_ORDER)},
    )
    left.plotly_chart(style_figure(priority_fig), width="stretch")

    behaviors = filter_frame(supervisor_frames["team_behavior_coverage"], stage_id)
    behavior_fig = px.bar(
        behaviors,
        x="behavior",
        y="value",
        color="series",
        barmode="group",
        title="Team behavior coverage",
        labels={"behavior": "Behavior", "value": "Share of calls", "series": "Series"},
        color_discrete_sequence=["#2563eb", "#94a3b8"],
    )
    right.plotly_chart(style_figure(behavior_fig, percent_axis=True), width="stretch")

    queue = filter_frame(supervisor_frames["coaching_queue"], stage_id)
    queue = queue.sort_values(["priority_rank", "agent_id"])
    st.subheader("Explainable coaching queue")
    st.dataframe(
        queue[
            [
                "agent_label",
                "priority",
                "focus_area",
                "why_now",
                "next_action",
                "guardrail",
                "calls_reviewed",
            ]
        ],
        hide_index=True,
        width="stretch",
    )

    review_calls = filter_frame(supervisor_frames["review_calls"], stage_id)
    queue_labels = sorted(review_calls["queue_label"].dropna().unique().tolist())
    selected_queue = st.selectbox("Call review queue", queue_labels)
    selected_calls = review_calls.loc[review_calls["queue_label"] == selected_queue]
    st.dataframe(
        selected_calls[
            [
                "agent_label",
                "selection",
                "call_id",
                "estimated_aht_sec",
                "heuristic_risk_score",
                "rubric_reasons",
                "evidence",
            ]
        ],
        hide_index=True,
        width="stretch",
    )


def render_survey_representativeness(
    survey_frames: dict[str, pd.DataFrame], stage_id: str, agent_id: str
) -> None:
    summary_rows = filter_frame(survey_frames["agent_summary"], stage_id, agent_id)
    if summary_rows.empty:
        st.warning("No survey representativeness summary is available for this view.")
        return
    summary = summary_rows.iloc[0]

    st.header("Survey Representativeness — Synthetic Demo")
    st.caption(
        f"Checks whether the surveyed subset resembles all analyzed calls for "
        f"{summary['agent_label']}. It does not score the agent or estimate real CSAT."
    )
    st.warning(
        "All surveys in this view are synthetic fixtures. The analysis demonstrates "
        "sample-selection safeguards and is not real customer feedback."
    )

    columns = st.columns(5)
    columns[0].metric("Calls analyzed", int(summary["calls_analyzed"]))
    columns[1].metric("Low review priority", f"{float(summary['low_share']):.0%}")
    columns[2].metric("Synthetic surveys", int(summary["surveys_received"]))
    columns[3].metric("Survey coverage", f"{float(summary['survey_coverage']):.0%}")
    gap = summary["elevated_share_gap"]
    columns[4].metric(
        "Survey mix gap",
        "Unavailable" if pd.isna(gap) else f"{float(gap):+.0%}",
        help="Surveyed medium/high share minus the medium/high share across all calls.",
    )

    signal = str(summary["representativeness_signal"])
    if signal.startswith("Skewed toward higher"):
        st.error(f"**Representativeness signal:** {signal}")
    elif signal.startswith("Skewed toward lower"):
        st.warning(f"**Representativeness signal:** {signal}")
    else:
        st.info(f"**Representativeness signal:** {signal}")
    st.markdown(f"**Interpretation:** {summary['interpretation']}")
    st.caption(
        f"Confidence: {summary['confidence']} — {summary['confidence_reason']}"
    )

    mix = filter_frame(survey_frames["risk_mix"], stage_id, agent_id)
    mix["risk_level"] = pd.Categorical(
        mix["risk_level"], categories=["low", "medium", "high"], ordered=True
    )
    mix = mix.sort_values(["risk_level", "population"])
    mix_fig = px.bar(
        mix,
        x="risk_level",
        y="share",
        color="population",
        barmode="group",
        title="Risk-proxy mix: all calls vs surveyed subset",
        labels={
            "risk_level": "Heuristic review priority",
            "share": "Share of calls",
            "population": "Population",
        },
        color_discrete_sequence=["#2563eb", "#f59e0b"],
    )
    st.plotly_chart(style_figure(mix_fig, percent_axis=True), width="stretch")

    surveyed = filter_frame(survey_frames["surveyed_calls"], stage_id, agent_id)
    st.subheader("Linked synthetic survey calls")
    if surveyed.empty:
        st.info("No synthetic survey calls are present in this analysis window.")
    else:
        display = surveyed[
            [
                "call_id",
                "agent_call_number",
                "heuristic_risk_score",
                "heuristic_risk_level",
                "synthetic_survey_positive",
                "survey_type",
                "is_synthetic",
            ]
        ].copy()
        display["synthetic_survey_result"] = display[
            "synthetic_survey_positive"
        ].map({1: "Positive synthetic", 0: "Negative synthetic"})
        st.dataframe(
            display.drop(columns=["synthetic_survey_positive"]),
            hide_index=True,
            width="stretch",
        )

    st.caption(
        "The signal uses a 20 percentage-point elevated-call mix gap or a 5-point "
        "average heuristic-risk gap. It is a transparent demo rule, not statistical proof."
    )


def render_agent_copilot(stage_id: str, agent_id: str) -> None:
    st.header("Agent Copilot")
    st.caption(
        "Ask grounded questions about the selected agent's KPIs, calls, coaching "
        "context, accumulated patterns, and portfolio policies. The model receives "
        "only controlled tool results."
    )

    mode_label = st.radio(
        "Response mode",
        list(COPILOT_MODES),
        horizontal=True,
        help=(
            "Local Qwen uses the llama.cpp server on this computer. If it is unavailable "
            "or its answer fails a guardrail, the service returns the deterministic fallback."
        ),
    )
    provider_name = COPILOT_MODES[mode_label]
    if provider_name == "llama_cpp_server":
        st.info(
            "Local Qwen mode selected. Start `scripts/start_local_model.ps1` in a "
            "separate VS Code terminal before sending a question."
        )
    else:
        st.info(
            "Deterministic mode demonstrates the same controlled retrieval, evidence, "
            "and policy tools without starting the local model."
        )

    question_columns = st.columns(4)
    suggestions = (
        "Analyze my accumulated patterns and coaching needs",
        "Show me evidence from my best and most coachable calls",
        "How should I improve AHT without sacrificing policy or service?",
        "Are my surveys representative of all my analyzed calls?",
    )
    selected_question: str | None = None
    for column, suggestion in zip(question_columns, suggestions):
        if column.button(suggestion, width="stretch"):
            selected_question = suggestion

    context_key = f"{provider_name}:{agent_id}:{stage_id}"
    histories = st.session_state.setdefault("copilot_histories", {})
    history = histories.setdefault(context_key, [])

    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                st.caption(message["metadata"])

    typed_question = st.chat_input("Ask about performance, coaching, calls, or policy")
    question = typed_question or selected_question
    if not question:
        return

    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    config_path = PROJECT_ROOT / "config" / "copilot_config.json"
    try:
        service = build_copilot_service(
            provider_name,
            KPI_ARTIFACT.stat().st_mtime_ns,
            SURVEY_ARTIFACT.stat().st_mtime_ns,
            MEMORY_ARTIFACT.stat().st_mtime_ns,
            config_path.stat().st_mtime_ns,
        )
        with st.chat_message("assistant"):
            with st.spinner("Retrieving grounded evidence..."):
                response = service.ask(question, agent_id, stage_id)
            st.markdown(response.answer)
            metadata = (
                f"Provider: {response.provider} · Tools: "
                f"{', '.join(response.tool_calls) or 'none'} · Grounded: yes"
            )
            st.caption(metadata)
            if response.fallback_reason:
                st.warning(f"Safe fallback used: {response.fallback_reason}")
            if response.citations:
                with st.expander("Evidence citations"):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "citation": citation.id,
                                    "source": citation.source,
                                    "locator": citation.locator,
                                    "note": citation.note,
                                }
                                for citation in response.citations
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )
        history.append(
            {
                "role": "assistant",
                "content": response.answer,
                "metadata": metadata,
            }
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        st.error(f"The Copilot could not answer: {exc}")


def render_supervisor_copilot(
    stage_id: str, agent_id: str | None = None
) -> None:
    st.header("Supervisor Copilot")
    scope_label = agent_id or "Entire team"
    st.caption(
        "Ask grounded questions about team metrics, agent context, coaching queues, "
        "review calls, and descriptive statistics. The agent can plan up to four "
        "read-only tool calls and never receives unrestricted database access."
    )
    st.info(
        f"Current scope: {scope_label}. Outputs support human review; they are not "
        "employee rankings or disciplinary decisions."
    )

    mode_label = st.radio(
        "Response mode",
        list(COPILOT_MODES),
        horizontal=True,
        key="supervisor_copilot_mode",
        help=(
            "Local Qwen selects a bounded tool plan and synthesizes the answer. "
            "If planning or generation fails, the safe deterministic workflow is used."
        ),
    )
    provider_name = COPILOT_MODES[mode_label]
    if provider_name == "llama_cpp_server":
        st.info(
            "Local Qwen mode selected. Start `scripts/start_local_model.ps1` in a "
            "separate VS Code terminal before sending a question."
        )

    suggestions = (
        "Summarize team health and the coaching queue",
        "Show descriptive team statistics and explain their limits",
        "Show the best calls that could support team feedback",
        (
            "Compare this agent with the team and recommend evidence to review"
            if agent_id
            else "Which team evidence deserves supervisor attention first?"
        ),
    )
    selected_question: str | None = None
    for column, suggestion in zip(st.columns(4), suggestions):
        if column.button(suggestion, width="stretch"):
            selected_question = suggestion

    context_key = f"{provider_name}:{agent_id or 'team'}:{stage_id}"
    histories = st.session_state.setdefault("supervisor_copilot_histories", {})
    history = histories.setdefault(context_key, [])
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                st.caption(message["metadata"])

    typed_question = st.chat_input(
        "Ask about the team, an agent, coaching evidence, calls, or statistics"
    )
    question = typed_question or selected_question
    if not question:
        return

    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    config_path = PROJECT_ROOT / "config" / "copilot_config.json"
    try:
        service = build_supervisor_agent_service(
            provider_name,
            SUPERVISOR_ARTIFACT.stat().st_mtime_ns,
            MEMORY_ARTIFACT.stat().st_mtime_ns,
            config_path.stat().st_mtime_ns,
        )
        with st.chat_message("assistant"):
            with st.spinner("Planning controlled tools and validating evidence..."):
                response = service.ask(question, stage_id, agent_id)
            st.markdown(response.answer)
            metadata = (
                f"Provider: {response.provider} | Scope: {response.agent_id} | Tools: "
                f"{', '.join(response.tool_calls) or 'none'} | Grounded: yes"
            )
            st.caption(metadata)
            if response.fallback_reason:
                st.warning(f"Safe fallback used: {response.fallback_reason}")
            if response.citations:
                with st.expander("Evidence citations"):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "citation": citation.id,
                                    "source": citation.source,
                                    "locator": citation.locator,
                                    "note": citation.note,
                                }
                                for citation in response.citations
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )
        history.append(
            {"role": "assistant", "content": response.answer, "metadata": metadata}
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        st.error(f"The Supervisor Copilot could not answer: {exc}")


def render_methodology(
    kpi: dict[str, Any], supervisor: dict[str, Any], survey: dict[str, Any]
) -> None:
    st.header("Methodology and limitations")
    st.markdown(
        """
        This application is a presentation layer over the checked-in analytical
        artifacts. It does not rerun transcription, sentiment analysis, acoustic
        extraction, the local LLM, or the risk rubric.

        **Interpretation boundaries**

        - `conversation_risk_v1` is an uncalibrated heuristic review proxy.
        - Estimated AHT is analyzed recording duration, not telephony-system AHT.
        - Behavior matches are coaching evidence, not official QA failures.
        - CSAT, QA, NPS, Five Stars, and supplied survey fixtures are synthetic.
        - Survey representativeness compares call-mix proxies; it does not model
          real survey response propensity or prove that survey arrival was random.
        - Agent comparisons are not adjusted for call mix or complexity.
        - A human reviewer must inspect cited call evidence before acting.
        """
    )

    sources = []
    for artifact_name, artifact in (
        ("Agent KPI", kpi),
        ("Supervisor", supervisor),
        ("Survey representativeness", survey),
    ):
        for source in artifact.get("sources", []):
            sources.append(
                {
                    "dashboard": artifact_name,
                    "source": source.get("label", source.get("id", "")),
                    "path": source.get("path", ""),
                }
            )
    st.subheader("Canonical sources")
    st.dataframe(pd.DataFrame(sources), hide_index=True, width="stretch")
    st.caption(
        f"KPI artifact: {format_timestamp(kpi.get('generatedAt'))} · "
        f"Supervisor artifact: {format_timestamp(supervisor.get('generatedAt'))} · "
        f"Survey artifact: {format_timestamp(survey.get('generatedAt'))}"
    )


def render_knowledge_base_admin() -> None:
    st.header("Knowledge Base Admin")
    st.caption(
        "Upload business documents for local, evidence-cited RAG retrieval. "
        "Files remain under the ignored `.runtime` directory and do not retrain Qwen."
    )
    st.warning(
        "Local portfolio control only: there is no enterprise authentication, malware "
        "scanner, OCR, or document-approval workflow in v1. Upload only documents you "
        "are authorized to use."
    )

    try:
        service = KnowledgeIngestionService()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        st.error(f"Knowledge ingestion is unavailable: {exc}")
        return
    contract = service.contract_summary()

    with st.form("knowledge_ingestion_form", clear_on_submit=False):
        identity_columns = st.columns(2)
        business_id = identity_columns[0].text_input(
            "Business ID",
            value=service.contract["default_business_id"],
            help="Lowercase stable identifier used to isolate documents between businesses.",
        )
        title = identity_columns[1].text_input("Document title")

        metadata_columns = st.columns(4)
        policy_type = metadata_columns[0].selectbox(
            "Document type", service.contract["allowed_policy_types"]
        )
        version = metadata_columns[1].text_input("Version", value="1.0")
        effective_date = metadata_columns[2].date_input(
            "Effective date", value=date.today()
        )
        language = metadata_columns[3].text_input("Language", value="en")

        market = st.text_input("Market", value="demo")
        uploaded = st.file_uploader(
            "Policy or playbook",
            type=[extension.lstrip(".") for extension in contract["allowed_extensions"]],
            help="PDF, DOCX, TXT, or Markdown; maximum 10 MB.",
        )
        approved = st.checkbox(
            "I confirm this document is approved for this local demo index",
            value=False,
            help=(
                "Unchecked documents are registered as pending review and remain "
                "unavailable to the Copilot."
            ),
        )
        submitted = st.form_submit_button("Process document", type="primary")

    if submitted:
        if uploaded is None:
            st.error("Select a document before processing.")
        else:
            try:
                record = service.ingest_bytes(
                    uploaded.name,
                    uploaded.getvalue(),
                    {
                        "business_id": business_id,
                        "title": title,
                        "policy_type": policy_type,
                        "version": version,
                        "effective_date": effective_date.isoformat(),
                        "language": language,
                        "market": market,
                        "approval_status": (
                            "approved_demo" if approved else "pending_review"
                        ),
                    },
                )
                build_copilot_service.clear()
                if record["indexed_for_retrieval"]:
                    st.success(
                        f"Indexed {record['title']} v{record['version']} in "
                        f"{record['chunk_count']} retrievable chunks."
                    )
                else:
                    st.info(
                        f"Registered {record['title']} v{record['version']} as pending "
                        "review. It is not available to the Copilot."
                    )
            except (KnowledgeIngestionError, OSError, ValueError) as exc:
                st.error(f"Document was not indexed: {exc}")

    try:
        normalized_business = service.store.validate_business_id(business_id)
        documents = service.store.list_documents(normalized_business)
        approved_documents = [
            item for item in documents if item["indexed_for_retrieval"]
        ]
        approved_chunks = service.store.list_chunks(
            normalized_business, approved_only=True
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        st.error(f"The business registry could not be read: {exc}")
        return

    metric_columns = st.columns(3)
    metric_columns[0].metric("Uploaded documents", len(documents))
    metric_columns[1].metric("Approved documents", len(approved_documents))
    metric_columns[2].metric("Retrievable chunks", len(approved_chunks))

    st.subheader("Local document registry")
    if documents:
        registry_rows = [
            {
                "title": item["title"],
                "version": item["version"],
                "type": item["policy_type"],
                "effective_date": item["effective_date"],
                "market": item["market"],
                "status": item["approval_status"],
                "chunks": item["chunk_count"],
                "source": item["source_filename"],
            }
            for item in documents
        ]
        st.dataframe(pd.DataFrame(registry_rows), hide_index=True, width="stretch")
    else:
        st.info("No local documents have been uploaded for this business.")

    st.subheader("Test retrieval")
    query = st.text_input(
        "Search approved knowledge",
        placeholder="Example: When is supervisor approval required?",
    )
    if query.strip():
        try:
            results = PolicyRetriever(business_id=normalized_business).search(query)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            st.error(f"Retrieval failed: {exc}")
        else:
            if not results:
                st.warning("No approved passage matched this query.")
            else:
                result_rows = [
                    {
                        "document": item.document,
                        "title": item.heading,
                        "version": item.version,
                        "page": item.page,
                        "source_type": item.source_type,
                        "passage": item.text[:400],
                    }
                    for item in results
                ]
                st.dataframe(pd.DataFrame(result_rows), hide_index=True, width="stretch")
                st.caption(
                    "Search is lexical in v1. Semantic embeddings and a vector store "
                    "remain optional future adapters."
                )


def main() -> None:
    st.set_page_config(
        page_title="AI Analyzer — Customer Service Intelligence",
        page_icon="📊",
        layout="wide",
    )
    st.title("AI Analyzer")
    st.caption("Evidence-first customer service intelligence and coaching portfolio")

    try:
        kpi, supervisor, survey = load_artifacts()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        st.error(f"The dashboard could not load its canonical artifacts: {exc}")
        st.stop()

    kpi_frames = dataset_frames(kpi)
    supervisor_frames = dataset_frames(supervisor)
    survey_frames = dataset_frames(survey)
    stages = stage_labels(kpi_frames["kpi_summary"])

    st.sidebar.header("Navigation")
    page = st.sidebar.radio(
        "View",
        (
            "Executive overview",
            "KPI Performance Tracker",
            "Survey Representativeness",
            "Agent Copilot",
            "Supervisor Board",
            "Supervisor Copilot",
            "Knowledge Base Admin",
            "Methodology",
        ),
    )
    stage_id = st.sidebar.selectbox(
        "Analysis window",
        list(stages),
        index=len(stages) - 1,
        format_func=lambda value: stages[value],
        disabled=page in {"Knowledge Base Admin", "Methodology"},
    )

    agent_id: str | None = None
    if page in {
        "KPI Performance Tracker",
        "Survey Representativeness",
        "Agent Copilot",
    }:
        agents = (
            kpi_frames["kpi_summary"][["agent_id", "agent_label"]]
            .drop_duplicates()
            .sort_values("agent_id")
        )
        agent_labels = dict(zip(agents["agent_id"], agents["agent_label"]))
        agent_id = st.sidebar.selectbox(
            "Agent", list(agent_labels), format_func=lambda value: agent_labels[value]
        )

    supervisor_agent_id: str | None = None
    if page == "Supervisor Copilot":
        agents = (
            kpi_frames["kpi_summary"][["agent_id", "agent_label"]]
            .drop_duplicates()
            .sort_values("agent_id")
        )
        supervisor_agent_labels = dict(zip(agents["agent_id"], agents["agent_label"]))
        supervisor_scope = st.sidebar.selectbox(
            "Supervisor scope",
            ["team", *supervisor_agent_labels],
            format_func=lambda value: (
                "Entire team" if value == "team" else supervisor_agent_labels[value]
            ),
        )
        supervisor_agent_id = None if supervisor_scope == "team" else supervisor_scope

    st.sidebar.divider()
    st.sidebar.caption(
        "Data source: checked-in analytical artifacts. No API key, GPU, or LLM is required."
    )

    if page == "Executive overview":
        render_executive_overview(kpi_frames, supervisor_frames, stage_id)
    elif page == "KPI Performance Tracker" and agent_id is not None:
        render_agent_tracker(kpi_frames, stage_id, agent_id)
    elif page == "Survey Representativeness" and agent_id is not None:
        render_survey_representativeness(survey_frames, stage_id, agent_id)
    elif page == "Agent Copilot" and agent_id is not None:
        render_agent_copilot(stage_id, agent_id)
    elif page == "Supervisor Board":
        render_supervisor_board(supervisor_frames, stage_id)
    elif page == "Supervisor Copilot":
        render_supervisor_copilot(stage_id, supervisor_agent_id)
    elif page == "Knowledge Base Admin":
        render_knowledge_base_admin()
    else:
        render_methodology(kpi, supervisor, survey)


if __name__ == "__main__":
    main()
