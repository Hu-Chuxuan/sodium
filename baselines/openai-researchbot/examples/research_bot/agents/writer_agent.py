# Agent used to synthesize a final report from the individual summaries.
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel

from agents import Agent, ModelSettings

PROMPT = (
    "You are a senior researcher tasked with writing a cohesive report for a research query. "
    "You will be provided with the original query, and some initial research done by a research "
    "assistant.\n"
    "You should first come up with an outline for the report that describes the structure and "
    "flow of the report. Then, generate the report and return that as your final output.\n"
    "You should also output a final answer that is very concise, can also be numeric values."
)


class ReportData(BaseModel):
    final_ans: str
    """The final answer, as concise as possible."""

    markdown_report: str
    """The final report"""


writer_agent = Agent(
    name="WriterAgent",
    instructions=PROMPT,
    model="gpt-5",
    model_settings=ModelSettings(reasoning=Reasoning(effort="medium")),
    output_type=ReportData,
)
