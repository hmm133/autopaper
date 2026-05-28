from __future__ import annotations

import json

from app.search.schemas import PaperCandidate, SearchRequest


def build_relevance_screening_messages(
    request: SearchRequest,
    candidates: list[PaperCandidate],
    schema: dict,
) -> list[dict[str, str]]:
    system_prompt = "\n".join(
        [
            "You are a question-driven literature relevance reranker.",
            "Score each candidate paper for relevance to the user's research question.",
            "First interpret the user's wording as a research scene or scenario, especially when it is colloquial, vague, or underspecified.",
            "Then infer the core research tasks or problems that belong to that scene.",
            "Use those inferred tasks to judge whether each paper is truly relevant.",
            "Use only the provided user intent and each paper's paper_id, title, and summary.",
            "Return only paper_id and score for each candidate.",
            "Return valid json that matches the schema exactly.",
            "Return json only. Do not wrap the json in markdown fences.",
            "Your output must be a single json object.",
        ]
    )

    compact_candidates = [
        {
            "paper_id": candidate.arxiv_id,
            "title": candidate.title,
            "summary": candidate.summary,
        }
        for candidate in candidates
    ]

    user_prompt = "\n".join(
        [
            "Task:",
            "Score each candidate paper for relevance to the user's literature search.",
            "Do not explain your reasoning.",
            "Do not add fields beyond paper_id and score.",
            "",
            "Scoring rule:",
            "- Use a score from 0 to 100.",
            "- 0 means completely irrelevant.",
            "- 100 means highly relevant and central to the search.",
            "- If the user's wording is colloquial or vague, first map it to the likely research scene, then to the likely tasks or problems, and score the paper against that inferred scene-task space.",
            "- A paper can be relevant even if it does not share the exact user wording, as long as it matches the inferred scene and core task.",
            "- Score all candidates in one pass.",
            "",
            "User intent:",
            json.dumps(
                {
                    "topic_description": request.topic_description,
                    "search_intent": request.search_intent,
                    "authors": request.authors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Candidate papers:",
            json.dumps(compact_candidates, ensure_ascii=False, indent=2),
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Rules:",
            "- Return one score entry for every candidate paper_id.",
            "- Keep the order stable if possible.",
            "- Use only the provided information.",
        ]
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
