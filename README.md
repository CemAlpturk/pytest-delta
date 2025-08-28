# pytest-delta

Run only tests impacted by your code changes. Speed up CI dramatically by pruning irrelevant tests using a lightweight dependency graph + git diff.

## Quickstart

```bash
pip install pytest-delta
pytest --delta --delta-base origin/main
