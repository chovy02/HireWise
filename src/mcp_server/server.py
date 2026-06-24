from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "HireWise MCP Server",
    host="0.0.0.0",
    port=8001
)


@mcp.tool()
def hello_hirewise(name: str) -> str:
    """
    Say hello to a HireWise user.
    """
    return f"Hello {name}, HireWise MCP Server is running successfully."


@mcp.tool()
def generate_interview_questions(job_title: str, skill: str) -> list[str]:
    """
    Generate simple interview questions based on a job title and one skill.
    """
    return [
        f"Can you introduce your experience related to the {job_title} position?",
        f"Can you describe a project where you used {skill}?",
        f"What difficulties did you face when working with {skill}?",
        f"How would you apply {skill} in a real company project?",
        f"Why do you think you are suitable for the {job_title} position?"
    ]


if __name__ == "__main__":
    mcp.run(transport="sse")