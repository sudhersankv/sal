TASK = uv run python scripts/tasks.py
.PHONY: mcp bot setup seed dev ui tools vendors week record demo check
setup:
	$(TASK) setup
seed:
	$(TASK) seed
dev:
	$(TASK) dev
ui:
	$(TASK) ui
tools:
	$(TASK) tools
vendors:
	$(TASK) vendors
week:
	$(TASK) week
record:
	$(TASK) record
demo:
	$(TASK) demo
check:
	$(TASK) check
bot:
	$(TASK) bot
mcp:
	$(TASK) mcp
