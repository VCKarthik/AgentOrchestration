def estimate_task_hours(task_description: str) -> int:
    text = task_description.lower()

    if "urgent" in text or "critical" in text:
        return 8
    elif "issue" in text or "bug" in text:
        return 4
    elif "update" in text or "follow up" in text:
        return 2
    else:
        return 3