"""Fail-fast tombstone for the retired conversation-continuity configurator.

Fresh native deployments use the selected host's native state and independent
UI metadata flags. This command never reads Azure state, transfers data,
reconciles assignments, provisions secrets, or deletes resources.
"""


def main(*, activate: bool = False) -> None:
    raise ValueError(
        "The conversation-continuity configurator is obsolete. Configure "
        "ORCHESTRATION_HOST=hosted|container_apps and "
        "APPLICATION_MODE=conversational|workflow|both; "
        "ENABLE_CHAT_HISTORY is independent and defaults to false."
    )


if __name__ == "__main__":
    main()
