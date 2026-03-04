from app.engine.github import build_pr_body


def test_build_pr_body():
    body = build_pr_body(
        feature_name="add login",
        spec="Login spec...",
        architecture="Architecture notes...",
        gate_result={"total_score": 14, "decision": "PASS"},
    )
    assert "add login" in body
    assert "PASS" in body
    assert "Login spec" in body
