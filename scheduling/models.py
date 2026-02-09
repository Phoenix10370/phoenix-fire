from django.conf import settings
from django.db import models

class ScheduledWork(models.Model):
    """
    One scheduled block of time on the calendar.

    Assumes you already have some model like JobTask/WorkOrderTask.
    Replace 'jobs.JobTask' with your real model label.
    """
    job_task = models.OneToOneField("job_tasks.JobTask", on_delete=models.CASCADE, related_name="schedule")


    start = models.DateTimeField()
    end = models.DateTimeField()

    # Optional but useful
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_works",
    )

    # Store a color for consistent rendering (per job/service type/etc.)
    color = models.CharField(max_length=7, blank=True, default="")  # e.g. "#1f77b4"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["start"]),
            models.Index(fields=["end"]),
        ]

    def __str__(self):
        return f"{self.job_task} ({self.start} - {self.end})"
