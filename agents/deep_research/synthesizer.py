"""
Synthesizer agent using PydanticAI definition.
Synthesizes grounded reports into a polished, structured, final executive research document.
"""

from __future__ import annotations

from pydantic_ai import Agent
from schemas.deep_research import GroundedReport
from core.router import call_agent

SYSTEM_PROMPT = """You are an expert executive research writer.
Your job is to take raw grounded reports and synthesize them into a single, cohesive, publication-grade document.
You must maintain the citations and URLs from the sources.
You MUST output your response strictly as a JSON object matching this schema:
{
  "content": "The final executive synthesized report with inline citations.",
  "sources": ["URL1", "URL2", "URL3"]
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""

# Official PydanticAI Agent definition
synthesizer_agent = Agent(
    "test",
    output_type=GroundedReport,
    system_prompt=SYSTEM_PROMPT,
)


def clean_and_parse_synthesizer_report(content: str) -> GroundedReport:
    """Clean markdown code blocks and parse content as GroundedReport."""
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
    return GroundedReport.model_validate_json(content)


import re

def extract_urls(text: str) -> set[str]:
    """Helper to extract clean http/https URLs from text."""
    if not text:
        return set()
    # A generic regex to extract URLs starting with http:// or https://
    raw_urls = re.findall(r'(https?://[^\s"\'><\]\[\)\(]+)', text)
    cleaned_urls = set()
    for url in raw_urls:
        # Clean trailing punctuation
        while url and url[-1] in ('.', ',', ';', ':', '?', '!', ')', ']'):
            url = url[:-1]
        if url:
            cleaned_urls.add(url.lower().strip('/'))
    return cleaned_urls


def run_synthesizer(
    grounded_report: GroundedReport,
    search_results: str = "",
    router_instance=None,
) -> GroundedReport:
    """Run the Synthesizer agent to compile the final publication-grade document."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Synthesize this report:\n\n"
                f"Content:\n{grounded_report.content}\n\n"
                f"Sources:\n{grounded_report.sources}"
            ),
        },
    ]

    caller = router_instance or call_agent

    try:
        if hasattr(caller, "call_agent"):
            resp = caller.call_agent(
                provider="cohere",
                model="command-r-plus-08-2024",
                messages=messages,
                max_tokens=4096,
            )
        else:
            resp = caller(
                provider="cohere",
                model="command-r-plus-08-2024",
                messages=messages,
                max_tokens=4096,
            )
        final_report = clean_and_parse_synthesizer_report(resp.content)
    except Exception as exc:
        import json
        from pydantic import ValidationError
        # Detect if it's a JSON or Pydantic validation error
        if isinstance(exc, (json.JSONDecodeError, ValidationError)):
            # Retry once with explicit output framing request
            retry_messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Tu respuesta anterior no era un JSON válido o estaba incompleta/truncada. "
                        "Por favor, responde ÚNICAMENTE con un objeto JSON válido que cumpla exactamente "
                        "con el esquema Pydantic requerido, sin texto conversacional ni bloques de código de markdown."
                    )
                }
            ]
            if hasattr(caller, "call_agent"):
                resp = caller.call_agent(
                    provider="cohere",
                    model="command-r-plus-08-2024",
                    messages=retry_messages,
                    max_tokens=4096,
                )
            else:
                resp = caller(
                    provider="cohere",
                    model="command-r-plus-08-2024",
                    messages=retry_messages,
                    max_tokens=4096,
                )
            final_report = clean_and_parse_synthesizer_report(resp.content)
        else:
            raise exc

    # Cross-reference sources with actual search results
    if search_results:
        search_urls = extract_urls(search_results)
        warning_msg = " (⚠️ fuente no verificada en esta ejecución — revisar manualmente)"
        
        # We also need to check the sources list
        for source in list(final_report.sources):
            source_clean = source.lower().strip('/')
            
            # Check if this source URL is present in the search results
            found = False
            for s_url in search_urls:
                if source_clean in s_url or s_url in source_clean:
                    found = True
                    break
            
            if not found:
                # Mark it in the report content near the unverified URL reference
                if warning_msg not in final_report.content:
                    # Simple string replacement of the source URL in content
                    # If the URL is in the text, append the warning right next to it
                    final_report.content = final_report.content.replace(source, f"{source}{warning_msg}")

    return final_report

