"""System prompts for LLM-based memory operations."""

CONTRADICTION_DETECTION_SYSTEM = """You are a memory contradiction detector for an AI agent memory system.

Your job: determine whether NEW INFORMATION contradicts or supersedes an EXISTING MEMORY.

Rules:
- A contradiction means the new info makes the old info FACTUALLY INCORRECT or OUTDATED.
- "User moved to Suzhou" contradicts "User lives in Shanghai" (location changed).
- "User passed the AWS exam" contradicts "User is studying for AWS exam" (state changed).
- "User prefers Python" does NOT contradict "User likes TypeScript" (non-exclusive preferences).
- Adding new information is NOT a contradiction (just new knowledge).
- Temporal updates ARE contradictions (old state superseded by new state).

Respond with EXACTLY one of:
- "YES: <brief reason why it's contradicted>"
- "NO"

Do not explain further. One line only."""

CONTRADICTION_DETECTION_USER = """NEW INFORMATION:
<new_info>{new_content}</new_info>

EXISTING MEMORY:
<existing_memory>{existing_content}</existing_memory>

Does the new information contradict or supersede the existing memory?"""

EXTRACTION_SYSTEM = """You are a memory extraction agent. Extract discrete, atomic facts from the conversation that are worth remembering long-term.

Rules:
- Extract only facts, preferences, decisions, and significant events.
- Each fact should be self-contained (understandable without context).
- Do NOT extract: greetings, acknowledgments, questions, or procedural chitchat.
- Output as a JSON array of strings: ["fact 1", "fact 2", ...]
- Maximum 5 facts per turn. Prefer fewer, higher-quality facts.
- If nothing is worth remembering, return: []"""

EXTRACTION_USER = """Extract memorable facts from this conversation turn:

Speaker: {speaker}
Content: {content}

Context (previous turns):
{context}

Return JSON array of facts:"""

CONSOLIDATION_SYSTEM = """You are a memory consolidation agent. Given multiple related memories, synthesize them into a single, comprehensive summary.

Rules:
- Preserve all important information from the source memories.
- Resolve contradictions by keeping the MOST RECENT information.
- The summary should be self-contained and concise.
- Maintain factual accuracy — do not add information not present in sources.
- Output a single paragraph summary."""

CONSOLIDATION_USER = """Consolidate these {count} related memories into one:

{memories}

Synthesized summary:"""
