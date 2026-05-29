import pytest

from retro_git.llm.plan_parse import coerce_plan_dict, parse_plan_json
from retro_git.models import DevelopmentPlan


def test_coerce_plan_dict_drops_malformed_commits_and_salvages_paths() -> None:
    data = {
        "project_summary": "test",
        "detected_stack": ["python"],
        "commits": [
            {
                "order": 1,
                "message": "chore: init",
                "files": ["README.md"],
            },
            {
                ".coverage": {"files": ["src/porch_alert/main.py"]},
                "tests/test_main.py": [],
            },
        ],
    }
    coerced = coerce_plan_dict(data)
    assert len(coerced["commits"]) == 1
    files = coerced["commits"][0]["files"]
    assert "README.md" in files
    assert "src/porch_alert/main.py" in files


def test_parse_plan_json_validates_development_plan() -> None:
    raw = """{
      "project_summary": "x",
      "detected_stack": [],
      "commits": [{"order": 1, "message": "feat: start", "files": ["a.py"]}]
    }"""
    plan = parse_plan_json(raw)
    assert isinstance(plan, DevelopmentPlan)
    assert plan.commits[0].message == "feat: start"


def test_coerce_plan_dict_raises_when_no_valid_commits() -> None:
    with pytest.raises(ValueError, match="no valid commits"):
        coerce_plan_dict({"commits": [{".coverage": {"files": ["a.py"]}}]})
