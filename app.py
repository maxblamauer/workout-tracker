#!/usr/bin/env python3
"""Workout Tracker — macOS menu bar app for tracking push/pull/legs rotation."""

import datetime
import rumps
import firebase_admin
from firebase_admin import credentials, firestore
# --- Firebase Setup ---

CONFIG_DIR = "~/.config/workout-tracker"
KEY_PATH = f"{CONFIG_DIR}/firebase-key.json"

DEFAULT_CYCLE = ["push", "pull", "legs"]


def init_firebase():
    """Initialize Firebase and return Firestore client."""
    import os
    key_path = os.path.expanduser(KEY_PATH)
    if not os.path.exists(key_path):
        rumps.alert(
            title="Firebase Key Missing",
            message=f"Place your Firebase service account key at:\n{key_path}\n\nSee setup instructions.",
        )
        return None
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def get_state(db):
    """Read current cycle and position from Firestore."""
    doc = db.collection("tracker").document("state").get()
    if doc.exists:
        return doc.to_dict()
    # First run — initialize default state
    state = {"cycle": DEFAULT_CYCLE, "position": 0, "last_log_date": None, "rest_days_per_week": 2}
    db.collection("tracker").document("state").set(state)
    return state


def save_state(db, state):
    """Persist state back to Firestore."""
    db.collection("tracker").document("state").set(state)


def log_entry(db, workout_type, status, date=None):
    """Write a workout log entry."""
    if date is None:
        date = datetime.date.today()
    db.collection("logs").add({
        "date": date.isoformat(),
        "workout_type": workout_type,
        "status": status,
        "created_at": firestore.SERVER_TIMESTAMP,
    })


def get_history(db, limit=10):
    """Fetch recent log entries."""
    docs = (
        db.collection("logs")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    entries = []
    for doc in docs:
        d = doc.to_dict()
        entries.append(d)
    return entries


# --- Menu Bar App ---

class WorkoutTracker(rumps.App):
    def __init__(self):
        self.db = init_firebase()
        if not self.db:
            super().__init__("Workout", quit_button=None)
            return

        self.state = get_state(self.db)
        self.cycle = self.state["cycle"]
        self.position = self.state["position"]

        current = self.current_workout()
        super().__init__(f"🏋️ {current.title()}", quit_button=None)

        self._build_menu()

        # Hide Dock icon once the run loop starts (delay so menu bar item exists first)
        self._hide_dock_timer = rumps.Timer(self._hide_dock_icon, 1)
        self._hide_dock_timer.start()

        # Check for missed days after app is fully running
        self._missed_days_timer = rumps.Timer(self._deferred_missed_check, 2)
        self._missed_days_timer.start()

    def _hide_dock_icon(self, _):
        """Remove the Dock icon after the menu bar is set up."""
        import AppKit
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        self._hide_dock_timer.stop()

    def _deferred_missed_check(self, _):
        """Run missed days check after the app is fully set up."""
        self._missed_days_timer.stop()
        self._check_missed_days()

    def current_workout(self):
        return self.cycle[self.position % len(self.cycle)]

    def _logged_today(self):
        """Check if there's already a log entry for today."""
        today = datetime.date.today().isoformat()
        return self.state.get("last_log_date") == today

    def _get_streak(self):
        """Count consecutive days with a 'done' entry (including today)."""
        entries = get_history(self.db, limit=60)
        if not entries:
            return 0
        streak = 0
        expected = datetime.date.today()
        for entry in entries:
            try:
                entry_date = datetime.date.fromisoformat(entry.get("date", ""))
            except (ValueError, TypeError):
                break
            if entry_date != expected:
                break
            if entry.get("status") == "done":
                streak += 1
            expected -= datetime.timedelta(days=1)
        return streak

    def _rest_days_this_week(self):
        """Count rest days taken in the current Mon-Sun week."""
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        entries = get_history(self.db, limit=30)
        count = 0
        for entry in entries:
            try:
                entry_date = datetime.date.fromisoformat(entry.get("date", ""))
            except (ValueError, TypeError):
                continue
            if monday <= entry_date <= today and entry.get("status") == "rest":
                count += 1
        return count

    def _get_week_schedule(self):
        """Build a Mon-Sun schedule with predicted rest days."""
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        done_today = self._logged_today()

        # Get this week's log entries
        entries = get_history(self.db, limit=30)
        logged = {}
        for entry in entries:
            date_str = entry.get("date", "")
            if date_str not in logged:
                logged[date_str] = entry

        # Collect indices of unlogged days (today if not logged + future)
        unlogged = []
        for i in range(7):
            day = monday + datetime.timedelta(days=i)
            day_str = day.isoformat()
            if day_str not in logged and day >= today:
                unlogged.append(i)

        # Predict which unlogged days are rest days
        rest_target = self.state.get("rest_days_per_week", 2)
        rest_taken = self._rest_days_this_week()
        rest_remaining = max(0, rest_target - rest_taken)

        rest_indices = set()
        if rest_remaining > 0 and len(unlogged) > 0:
            # Space rest days evenly among unlogged days
            step = len(unlogged) / rest_remaining
            for i in range(rest_remaining):
                idx = int(round(step * (i + 1))) - 1
                idx = min(idx, len(unlogged) - 1)
                rest_indices.add(unlogged[idx])

        # Build schedule lines, advancing cycle only for non-rest days
        cycle_pos = self.position
        if done_today:
            # Position already advanced from today's log
            cycle_pos = (self.position - 1) % len(self.cycle)

        days = []
        for i in range(7):
            day = monday + datetime.timedelta(days=i)
            day_str = day.isoformat()
            day_label = day.strftime("%a")
            entry = logged.get(day_str)

            if entry:
                status = entry.get("status", "")
                wtype = entry.get("workout_type", "?").title()
                mark = "+" if status == "done" else "-"
                line = f"  {day_label}  {mark}  {wtype}"
                if status == "done":
                    cycle_pos = (cycle_pos + 1) % len(self.cycle)
            elif day < today:
                line = f"  {day_label}  ·  —"
            elif i in rest_indices:
                line = f"  {day_label}  ·  Rest"
            else:
                wtype = self.cycle[cycle_pos % len(self.cycle)].title()
                line = f"  {day_label}  ·  {wtype}"
                cycle_pos = (cycle_pos + 1) % len(self.cycle)

            if day == today:
                line += "  ←"
            days.append(line)
        return days

    def _check_missed_days(self):
        """Check for days since last log and prompt per missed day."""
        last_log_date = self.state.get("last_log_date")
        if not last_log_date:
            return

        try:
            last = datetime.date.fromisoformat(last_log_date)
        except (ValueError, TypeError):
            return

        today = datetime.date.today()
        gap = (today - last).days

        if gap <= 1:
            return

        changed = False
        for i in range(1, gap):
            missed_date = last + datetime.timedelta(days=i)
            workout = self.cycle[self.position % len(self.cycle)]
            day_label = missed_date.strftime("%A %b %-d")

            response = rumps.alert(
                title=f"Missed: {day_label}",
                message=f"Scheduled workout: {workout.title()}\n\nDid you do it?",
                ok="Done",
                cancel="Skip",
                other="Rest",
            )

            if response == 1:  # Done
                log_entry(self.db, workout, "done", date=missed_date)
                self.position = (self.position + 1) % len(self.cycle)
                changed = True
            elif response == -1:  # Rest (other button)
                log_entry(self.db, "rest", "rest", date=missed_date)
                changed = True
            else:  # Skip
                log_entry(self.db, workout, "skip", date=missed_date)
                changed = True

        if changed:
            self.state["position"] = self.position
            self.state["last_log_date"] = (today - datetime.timedelta(days=1)).isoformat()
            save_state(self.db, self.state)
            self.refresh_menu()

    def _build_menu(self):
        """Build (or rebuild) the entire menu."""
        self.menu.clear()
        current = self.current_workout()
        done_today = self._logged_today()

        # Streak
        streak = self._get_streak()
        if streak > 0:
            self.menu.add(rumps.MenuItem(f"🔥 {streak} day streak", callback=None))
            self.menu.add(None)

        if done_today:
            entries = get_history(self.db, limit=1)
            logged_type = entries[0].get("workout_type", current).title() if entries else current.title()
            logged_status = entries[0].get("status", "") if entries else ""
            if logged_type.lower() == "rest" or logged_status == "rest":
                self.title = f"😴 Rest"
            else:
                self.title = f"✅ {logged_type}"
            self.menu.add(rumps.MenuItem("Today's workout logged!", callback=None))
            self.menu.add(None)
        else:
            self.title = f"🏋️ {current.title()}"
            self.menu.add(rumps.MenuItem(f"Today: {current.title()} Day", callback=None))
            self.menu.add(None)
            self.menu.add(rumps.MenuItem("✅ Done", callback=self.mark_done))
            self.menu.add(rumps.MenuItem("😴 Rest Instead", callback=self.mark_rest))
            self.menu.add(None)

        # Rest day counter
        rest_target = self.state.get("rest_days_per_week", 2)
        rest_taken = self._rest_days_this_week()
        self.menu.add(rumps.MenuItem(f"😴 Rest: {rest_taken}/{rest_target} this week", callback=None))
        self.menu.add(None)

        # Cycle rotation
        cycle_menu = rumps.MenuItem("— Rotation —")
        for i, w in enumerate(self.cycle):
            arrow = "→ " if i == (self.position % len(self.cycle)) else "    "
            cycle_menu.add(rumps.MenuItem(f"{arrow}🏋️ {w.title()}", callback=None))
        self.menu.add(cycle_menu)
        self.menu.add(None)

        self.menu.add(rumps.MenuItem("📅 View Schedule", callback=self.show_schedule))
        self.menu.add(rumps.MenuItem("Edit Cycle...", callback=self.edit_cycle))
        self.menu.add(rumps.MenuItem("Rest Days/Week...", callback=self.edit_rest_target))
        self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application))

    def show_schedule(self, _):
        """Show the weekly schedule in a dialog."""
        lines = self._get_week_schedule()
        today = datetime.date.today()
        week_label = f"Week of {(today - datetime.timedelta(days=today.weekday())).strftime('%b %-d')}"
        rest_target = self.state.get("rest_days_per_week", 2)
        rest_taken = self._rest_days_this_week()
        lines.append("")
        lines.append(f"  😴 Rest days: {rest_taken}/{rest_target}")
        rumps.alert(
            title=f"📅 {week_label}",
            message="\n".join(lines),
            ok="OK",
        )

    def refresh_menu(self):
        """Rebuild the full menu to reflect updated state."""
        self._build_menu()

    def mark_done(self, _):
        """Log workout as done and advance the rotation."""
        if self._logged_today():
            return
        workout = self.current_workout()
        log_entry(self.db, workout, "done")


        # Advance position
        self.position = (self.position + 1) % len(self.cycle)
        self.state["position"] = self.position
        self.state["last_log_date"] = datetime.date.today().isoformat()
        save_state(self.db, self.state)

        rumps.notification(
            title="Workout Logged 💪",
            subtitle=f"{workout.title()} — Done!",
            message=f"Next up: {self.current_workout().title()}",
        )
        self.refresh_menu()

    def mark_rest(self, _):
        """Log an unscheduled rest day — position does NOT advance."""
        if self._logged_today():
            return
        workout = self.current_workout()
        log_entry(self.db, "rest", "rest")

        self.state["last_log_date"] = datetime.date.today().isoformat()
        save_state(self.db, self.state)

        rumps.notification(
            title="Rest Day 😴",
            subtitle=f"{workout.title()} stays queued",
            message="Recovery is part of the process!",
        )
        self.refresh_menu()

    def edit_cycle(self, _):
        """Let the user edit the workout cycle via a dialog."""
        current_cycle = ", ".join(self.cycle)
        response = rumps.Window(
            title="Edit Workout Cycle",
            message="Enter workout types separated by commas.\n\nExample: push, pull, legs",
            default_text=current_cycle,
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 24),
        ).run()

        if response.clicked:
            new_cycle = [w.strip().lower() for w in response.text.split(",") if w.strip()]
            if new_cycle:
                self.cycle = new_cycle
                self.position = 0
                self.state["cycle"] = self.cycle
                self.state["position"] = 0
                save_state(self.db, self.state)
                self.refresh_menu()
                rumps.notification(
                    title="Cycle Updated",
                    subtitle=f"New cycle: {', '.join(w.title() for w in self.cycle)}",
                    message="Position reset to start.",
                )

    def edit_rest_target(self, _):
        """Let the user set rest days per week target."""
        current = self.state.get("rest_days_per_week", 2)
        response = rumps.Window(
            title="Rest Days Per Week",
            message="How many rest days per week?",
            default_text=str(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(100, 24),
        ).run()

        if response.clicked:
            try:
                new_target = int(response.text.strip())
                if 0 <= new_target <= 7:
                    self.state["rest_days_per_week"] = new_target
                    save_state(self.db, self.state)
                    self.refresh_menu()
            except ValueError:
                pass


if __name__ == "__main__":
    WorkoutTracker().run()
