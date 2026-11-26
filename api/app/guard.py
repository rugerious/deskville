"""Bedrock Guardrails around the assistant (D43, D44). The question is checked before
anything is searched or generated; the answer is checked against exactly what the model
was given. Fail closed: if the guardrail can't be reached, the assistant doesn't answer."""
import json


class GuardUnavailable(Exception):
    pass


def _reasons(out):
    found = []
    for a in out.get("assessments", []):
        found += [f"topic:{t['name']}" for t in a.get("topicPolicy", {}).get("topics", [])]
        found += [f"content:{f['type']}" for f in a.get("contentPolicy", {}).get("filters", [])
                  if f.get("action") == "BLOCKED"]
        found += [f"pii:{p['type']}" for p in a.get("sensitiveInformationPolicy", {}).get("piiEntities", [])]
        found += [f"{g['type'].lower()}:{g['score']:.2f}" for g in
                  a.get("contextualGroundingPolicy", {}).get("filters", []) if g.get("action") == "BLOCKED"]
    return found


def grounding_text(chunks, tools):
    parts = [f"{c['heading']}\n{c['text']}" for c in chunks]
    parts += [json.dumps(t, sort_keys=True) for t in tools]
    return "\n\n".join(parts) or "(no sources)"


class BedrockGuard:
    def __init__(self, region, guardrail_id, version):
        import boto3
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.id, self.version = guardrail_id, version

    def _apply(self, source, content):
        try:
            out = self.client.apply_guardrail(guardrailIdentifier=self.id, guardrailVersion=self.version,
                                              source=source, content=content)
        except Exception as e:  # any failure to check is a failure to answer
            raise GuardUnavailable(type(e).__name__) from e
        if out["action"] == "GUARDRAIL_INTERVENED":
            message = " ".join(o["text"] for o in out.get("outputs", []) if "text" in o)
            return {"blocked": True, "message": message, "reasons": _reasons(out)}
        return {"blocked": False, "message": None, "reasons": []}

    def check_question(self, question):
        return self._apply("INPUT", [{"text": {"text": question}}])

    def check_answer(self, question, chunks, tools, answer):
        return self._apply("OUTPUT", [
            {"text": {"text": grounding_text(chunks, tools)[:100000], "qualifiers": ["grounding_source"]}},
            {"text": {"text": question, "qualifiers": ["query"]}},
            {"text": {"text": answer, "qualifiers": ["guard_content"]}}])


class FakeGuard:
    """Tests: blocks questions containing BLOCK-ME, answers when block_answers is set, and
    records exactly what it was asked to check."""
    def __init__(self):
        self.questions, self.answers = [], []
        self.block_answers = False
        self.down = False

    def check_question(self, question):
        if self.down:
            raise GuardUnavailable("test")
        self.questions.append(question)
        if "BLOCK-ME" in question:
            return {"blocked": True, "message": "Sorry, I can only help with everyday council services.",
                    "reasons": ["content:PROMPT_ATTACK"]}
        return {"blocked": False, "message": None, "reasons": []}

    def check_answer(self, question, chunks, tools, answer):
        if self.down:
            raise GuardUnavailable("test")
        self.answers.append({"question": question, "grounding": grounding_text(chunks, tools), "answer": answer})
        if self.block_answers:
            return {"blocked": True, "message": "Sorry, I couldn't give a reliable answer.",
                    "reasons": ["grounding:0.10"]}
        return {"blocked": False, "message": None, "reasons": []}
