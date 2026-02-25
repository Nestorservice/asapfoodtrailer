"""
ASAP Food Trailer - Analytics Service
Tracks page views, devices, sources, and generates dashboard data
"""

from collections import Counter
from datetime import datetime, timedelta, timezone


class AnalyticsService:
    """Processes and aggregates analytics data for the admin dashboard."""

    def aggregate_dashboard_data(self, events: list, days: int = 30) -> dict:
        """Aggregate analytics events into dashboard-ready data."""
        now = datetime.now(timezone.utc)
        today = now.date()

        # Daily views (last N days)
        daily_views = {}
        for i in range(min(days, 30)):  # Cap daily labels at 30 for readability
            day = today - timedelta(days=i)
            daily_views[day.isoformat()] = 0

        # Weekly views (last 4 weeks)
        weekly_views = {}
        for i in range(4):
            week_start = today - timedelta(days=today.weekday() + 7 * i)
            week_label = f"Week {week_start.strftime('%m/%d')}"
            weekly_views[week_label] = 0

        # Counters
        devices = Counter()
        sources = Counter()
        cities = Counter()
        page_views = Counter()

        for event in events:
            try:
                ts = event.get("timestamp", "")
                if isinstance(ts, str) and ts:
                    event_date = datetime.fromisoformat(
                        ts.replace("Z", "+00:00")
                    ).date()
                else:
                    continue

                # Daily
                day_key = event_date.isoformat()
                if day_key in daily_views:
                    daily_views[day_key] += 1

                # Weekly
                days_ago = (today - event_date).days
                week_index = days_ago // 7
                if week_index < 4:
                    week_start = today - timedelta(
                        days=today.weekday() + 7 * week_index
                    )
                    week_label = f"Week {week_start.strftime('%m/%d')}"
                    if week_label in weekly_views:
                        weekly_views[week_label] += 1

                # Aggregations
                devices[event.get("device_type", "unknown")] += 1
                sources[event.get("source", "direct")] += 1
                cities[event.get("location_city", "Unknown")] += 1
                page_views[event.get("page_path", "/")] += 1

            except (ValueError, AttributeError):
                continue

        # Calculate conversion rate
        total_views = len(events)
        leads_count = sum(
            1 for e in events if e.get("page_path", "").startswith("/api/leads")
        )
        conversion_rate = (leads_count / total_views * 100) if total_views > 0 else 0

        return {
            "total_views": total_views,
            "today_views": daily_views.get(today.isoformat(), 0),
            "conversion_rate": round(conversion_rate, 2),
            "daily_views": {
                "labels": list(reversed(list(daily_views.keys()))),
                "data": list(reversed(list(daily_views.values()))),
            },
            "weekly_views": {
                "labels": list(reversed(list(weekly_views.keys()))),
                "data": list(reversed(list(weekly_views.values()))),
            },
            "devices": {
                "labels": list(devices.keys()),
                "data": list(devices.values()),
            },
            "sources": {
                "labels": list(sources.keys()),
                "data": list(sources.values()),
            },
            "top_cities": {
                "labels": list(dict(cities.most_common(10)).keys()),
                "data": list(dict(cities.most_common(10)).values()),
            },
            "top_pages": dict(page_views.most_common(10)),
        }


analytics_service = AnalyticsService()
