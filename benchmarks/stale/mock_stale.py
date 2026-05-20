"""Generate synthetic STALE-format contradiction pairs for pipeline testing.

50 pairs: 25 true contradictions + 25 false (old but still true).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StalePair:
    old_memory: str
    new_information: str
    is_contradiction: bool
    category: str  # explicit, implicit, temporal, non_contradiction


def generate_mock_stale_pairs() -> list[StalePair]:
    """Generate 50 synthetic pairs for testing contradiction detection."""

    true_contradictions = [
        # Explicit contradictions (direct negation)
        StalePair("User lives in Shanghai", "I just moved to Suzhou last week", True, "explicit"),
        StalePair("User works at Amazon", "I started my new job at Google yesterday", True, "explicit"),
        StalePair("User is single", "I got married last month", True, "explicit"),
        StalePair("User drives a Toyota", "I sold my car and bought a Tesla", True, "explicit"),
        StalePair("User's favorite color is blue", "I've changed my mind, I prefer green now", True, "explicit"),

        # Implicit contradictions (state update)
        StalePair("User is studying for AWS SAA exam", "I passed my AWS SAA certification yesterday", True, "implicit"),
        StalePair("User is pregnant", "My baby was born last Tuesday", True, "implicit"),
        StalePair("User is looking for a new apartment", "I finally signed the lease on my new place", True, "implicit"),
        StalePair("User is interviewing at Microsoft", "I accepted the offer from Microsoft and start next Monday", True, "implicit"),
        StalePair("User is writing their thesis", "I submitted my thesis yesterday and it's done", True, "implicit"),

        # Temporal contradictions (time-bound info expired)
        StalePair("User has a meeting at 3pm today", "The meeting was cancelled, we'll reschedule for next week", True, "temporal"),
        StalePair("User is on vacation until Friday", "I'm back from vacation now, returned yesterday", True, "temporal"),
        StalePair("User's deadline is May 25th", "The deadline was extended to June 15th", True, "temporal"),
        StalePair("User is in Tokyo for a conference", "I flew back home to Shanghai yesterday", True, "temporal"),
        StalePair("CPT202 course is in progress", "CPT202 final exam is done, course completed", True, "temporal"),

        # More explicit
        StalePair("User prefers dark mode", "I switched to light mode, it's easier on my eyes during the day", True, "explicit"),
        StalePair("User uses VS Code", "I completely moved to Cursor as my main editor", True, "explicit"),
        StalePair("User's phone number is 138-xxxx-1234", "My new number is 139-xxxx-5678, I changed carriers", True, "explicit"),
        StalePair("User lives alone", "My roommate moved in last week", True, "explicit"),
        StalePair("User is vegetarian", "I started eating meat again after 3 years", True, "explicit"),

        # More implicit
        StalePair("User is preparing for GRE", "I took the GRE last Saturday, scored 325", True, "implicit"),
        StalePair("User is deciding between PhD programs", "I accepted the offer from CMU", True, "implicit"),
        StalePair("User is debugging a memory leak in the app", "Fixed the memory leak, it was a circular reference", True, "implicit"),
        StalePair("User is waiting for paper review results", "Our paper was accepted to CHI!", True, "implicit"),
        StalePair("User is learning Rust", "I've been writing Rust professionally for 6 months now", True, "implicit"),
    ]

    non_contradictions = [
        # Additional information (not contradicting)
        StalePair("User studied CS at XJTLU", "I'm now working at Amazon as a software engineer", False, "non_contradiction"),
        StalePair("User likes Python", "I also started learning TypeScript for frontend work", False, "non_contradiction"),
        StalePair("User lives in Shanghai", "I went to Beijing for a business trip last week", False, "non_contradiction"),
        StalePair("User is a software engineer", "I'm also doing an FYP research project on the side", False, "non_contradiction"),
        StalePair("User has a cat named Mochi", "I adopted a second cat, named her Luna", False, "non_contradiction"),

        # Related but non-contradictory updates
        StalePair("User is working on AMF project", "I added a new benchmark module to AMF today", False, "non_contradiction"),
        StalePair("User's supervisor is Brennan", "I had a meeting with Brennan about the paper timeline", False, "non_contradiction"),
        StalePair("User prefers dark mode", "I use dark mode in VS Code and light mode for documents", False, "non_contradiction"),
        StalePair("User graduated from XJTLU", "I'm now applying to grad schools in the US", False, "non_contradiction"),
        StalePair("User passed AWS SAA", "I'm now studying for the AWS Solutions Architect Professional", False, "non_contradiction"),

        # Temporal but non-contradictory (past events are still true)
        StalePair("User went to Tokyo in March", "I'm planning another trip to Osaka in September", False, "non_contradiction"),
        StalePair("User worked at Amazon in 2025", "I learned a lot about distributed systems at Amazon", False, "non_contradiction"),
        StalePair("User published a paper at CHI 2027", "I'm now working on a follow-up paper for IUI", False, "non_contradiction"),
        StalePair("User's first language is Chinese", "I also speak English fluently and some Japanese", False, "non_contradiction"),
        StalePair("User built a React app last year", "I'm now building a Python backend for a new project", False, "non_contradiction"),

        # Same topic, compatible information
        StalePair("User likes coffee", "I drink about 3 cups of coffee per day", False, "non_contradiction"),
        StalePair("User exercises regularly", "I ran a half marathon last weekend", False, "non_contradiction"),
        StalePair("User is interested in AI", "I've been reading papers about agent memory systems", False, "non_contradiction"),
        StalePair("User has a MacBook", "I also have a desktop PC for gaming", False, "non_contradiction"),
        StalePair("User uses Git for version control", "I started using GitHub Actions for CI/CD", False, "non_contradiction"),

        # Opinions that coexist
        StalePair("User thinks Python is great for prototyping", "Rust is better for production performance-critical code", False, "non_contradiction"),
        StalePair("User enjoys hiking", "I also like swimming and cycling", False, "non_contradiction"),
        StalePair("User prefers Linux for servers", "I use macOS for my development machine", False, "non_contradiction"),
        StalePair("User reads sci-fi novels", "I've been getting into non-fiction lately too", False, "non_contradiction"),
        StalePair("User is interested in HCI research", "I also find systems research fascinating", False, "non_contradiction"),
    ]

    return true_contradictions + non_contradictions
