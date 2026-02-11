# Workout Tracker

macOS menu bar app for tracking a push/pull/legs workout rotation.

## Features

- **Menu bar widget** — shows today's workout, log as done or rest
- **Cycle rotation** — customizable workout cycle (default: push, pull, legs)
- **Missed day detection** — prompts on launch for any unlogged days
- **Rest day tracking** — ad-hoc rest days with a weekly target (default: 2/week)
- **Weekly schedule** — view upcoming workouts with predicted rest days
- **Streak counter** — tracks consecutive workout days
- **Firebase backend** — state and logs persist to Firestore

## Setup

1. Place your Firebase service account key at `~/.config/workout-tracker/firebase-key.json`
2. Run the setup script:

```bash
./setup.sh
```

Or manually:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Auto-start on login

A LaunchAgent is included in `setup.sh` to start the app automatically on login.
