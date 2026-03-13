"""
CLI runner for A2A War Games simulations.

Usage:
    python -m backend.cli --project 1 --session 20 --rounds 3
    python -m backend.cli --project 1 --question "Should we adopt AI?" --rounds 2
    python -m backend.cli --project 1 --session 20 --continue  # resume existing session

Features:
    - Colored terminal output (agent names in unique colors)
    - Real-time streaming (tokens print as they arrive)
    - No browser or frontend needed
    - Progress indicator showing round/turn status
    - Summary statistics at the end (turns, tokens, timing)
"""

import argparse
import asyncio
import json
import logging
import sys
import time

logger = logging.getLogger(__name__)

# Terminal colors
COLORS = ['\033[36m', '\033[33m', '\033[35m', '\033[32m', '\033[34m', '\033[91m']
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'


def _stakeholder_to_dict(s):
    """Convert a Stakeholder ORM object to a dict for A2AEngine."""
    return {
        "slug": s.slug,
        "name": s.name,
        "system_prompt": s.system_prompt or "",
        "influence": s.influence or 0.5,
        "attitude": s.attitude or "neutral",
        "tts_voice": getattr(s, "tts_voice", None),
    }


def main():
    parser = argparse.ArgumentParser(
        description="A2A War Games CLI — run simulations from the terminal"
    )
    parser.add_argument("--project", type=int, required=True, help="Project ID")
    parser.add_argument("--session", type=int, default=None, help="Existing session ID (creates new if omitted)")
    parser.add_argument("--question", type=str, default=None, help="Question for new sessions")
    parser.add_argument("--rounds", type=int, default=3, help="Number of rounds (default: 3)")
    parser.add_argument("--agents-per-turn", type=int, default=3, help="Agents per turn (default: 3)")
    parser.add_argument("--continue-session", action="store_true", dest="continue_session",
                        help="Resume an existing session")
    parser.add_argument("--model", type=str, default=None, help="Override default model")
    parser.add_argument("--no-observer", action="store_true", help="Skip observer extraction (faster)")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--no-persist", action="store_true", help="Skip DB writes for messages")
    parser.add_argument("--verbose", action="store_true", help="Show observer data and timing per turn")

    args = parser.parse_args()

    if args.no_color:
        global COLORS, RESET, BOLD, DIM
        COLORS = [''] * 6
        RESET = ''
        BOLD = ''
        DIM = ''

    asyncio.run(run_cli(args))


async def run_cli(args):
    from backend.database import init_db, SessionLocal
    from backend.a2a.engine import A2AEngine
    from backend.models import Project, Session, Stakeholder, LLMSettings, Message

    init_db()
    db = SessionLocal()

    try:
        # Load project
        project = db.query(Project).filter_by(id=args.project).first()
        if not project:
            print(f"{BOLD}Error:{RESET} Project {args.project} not found.")
            sys.exit(1)

        stakeholders = db.query(Stakeholder).filter_by(
            project_id=args.project, is_active=True
        ).all()
        if not stakeholders:
            print(f"{BOLD}Error:{RESET} No active stakeholders for project {args.project}.")
            sys.exit(1)

        # Load LLM settings
        llm = db.query(LLMSettings).filter_by(is_active=True).first()
        if not llm:
            print(f"{BOLD}Error:{RESET} No active LLM settings. Configure one in the web UI.")
            sys.exit(1)

        # Create or load session
        if args.session:
            session = db.query(Session).filter_by(id=args.session).first()
            if not session:
                print(f"{BOLD}Error:{RESET} Session {args.session} not found.")
                sys.exit(1)
        else:
            question = args.question or f"Strategic discussion for {project.name}"
            session = Session(
                project_id=args.project,
                question=question,
                title=f"CLI session — {question[:80]}",
                status="pending",
                participants=json.dumps([s.slug for s in stakeholders]),
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            print(f"{DIM}Created session #{session.id}{RESET}")

        # Build engine
        default_model = args.model or llm.default_model
        feature_flags = llm.feature_flags_dict
        skip_observer = args.no_observer

        if args.continue_session:
            engine = await A2AEngine.resume_from_db(
                session_id=session.id,
                additional_rounds=args.rounds,
                stakeholders=[_stakeholder_to_dict(s) for s in stakeholders],
                project={"name": project.name, "organization": project.organization,
                          "context": project.context, "description": project.description},
                llm_base_url=llm.base_url, llm_api_key=llm.api_key,
                default_model=default_model, chairman_model=llm.chairman_model,
                agents_per_turn=args.agents_per_turn,
                temperature=llm.temperature, max_tokens=llm.max_tokens,
                project_id=args.project,
                skip_observer=skip_observer,
            )
            engine.feature_flags = feature_flags
            start_round = getattr(engine, "_start_round", 1)
        else:
            engine = A2AEngine(
                session_id=session.id,
                question=session.question,
                stakeholders=[_stakeholder_to_dict(s) for s in stakeholders],
                project={"name": project.name, "organization": project.organization,
                          "context": project.context, "description": project.description},
                llm_base_url=llm.base_url, llm_api_key=llm.api_key,
                default_model=default_model, chairman_model=llm.chairman_model,
                num_rounds=args.rounds, agents_per_turn=args.agents_per_turn,
                temperature=llm.temperature, max_tokens=llm.max_tokens,
                feature_flags=feature_flags,
                project_id=args.project,
                skip_observer=skip_observer,
            )
            start_round = 1

        # Update session status
        session.status = "running"
        db.commit()

        # Print header
        print(f"\n{BOLD}{'═' * 60}{RESET}")
        print(f"{BOLD}  A2A War Games — CLI Runner{RESET}")
        print(f"{BOLD}{'═' * 60}{RESET}")
        print(f"  Project:     {project.name}")
        print(f"  Session:     #{session.id}")
        print(f"  Question:    {session.question[:80]}")
        print(f"  Rounds:      {args.rounds}")
        print(f"  Agents:      {len(stakeholders)} ({args.agents_per_turn} per turn)")
        print(f"  Model:       {default_model}")
        print(f"  Observer:    {'OFF' if args.no_observer else 'ON'}")
        print(f"{BOLD}{'═' * 60}{RESET}\n")

        # Run the simulation
        agent_colors = {}
        color_idx = 0
        start_time = time.time()
        turn_count = 0
        current_round = 0

        run_kwargs = {"start_round": start_round} if args.continue_session else {}

        async for event in engine.run(**run_kwargs):
            event_type = event.get("event")
            data = event.get("data", {})

            if event_type == "turn_start":
                speaker = data.get("speaker_name", "Unknown")
                if speaker not in agent_colors:
                    agent_colors[speaker] = COLORS[color_idx % len(COLORS)]
                    color_idx += 1
                color = agent_colors[speaker]
                print(f"\n{color}{BOLD}[{speaker}]{RESET} {DIM}(thinking...){RESET}", end="", flush=True)

            elif event_type == "content_token":
                print(data.get("delta", ""), end="", flush=True)

            elif event_type == "turn_end":
                content = data.get("content", "")
                speaker_name = data.get("speaker_name", "Unknown")
                color = agent_colors.get(speaker_name, "")
                turn_count += 1
                # Print full content (in case streaming wasn't active)
                if content:
                    print(f"\n{color}{BOLD}[{speaker_name}]{RESET}")
                    # Indent content for readability
                    for line in content.split('\n'):
                        print(f"  {line}")
                print(f"{DIM}{'─' * 60}{RESET}")

                # Persist message to DB
                if not args.no_persist:
                    _persist_turn(db, session.id, data)

            elif event_type == "turn":
                # Moderator messages
                content = data.get("content", "")
                speaker_name = data.get("speaker_name", "Moderator")
                if speaker_name not in agent_colors:
                    agent_colors[speaker_name] = COLORS[color_idx % len(COLORS)]
                    color_idx += 1
                color = agent_colors[speaker_name]
                print(f"\n{color}{BOLD}[{speaker_name}]{RESET}")
                for line in content.split('\n'):
                    print(f"  {line}")
                print(f"{DIM}{'─' * 60}{RESET}")

                if not args.no_persist:
                    _persist_turn(db, session.id, data)

            elif event_type == "synthesis":
                current_round = data.get("round", current_round + 1)
                print(f"\n{BOLD}{'═' * 60}{RESET}")
                print(f"{BOLD}  ROUND {current_round} SYNTHESIS{RESET}")
                print(f"{BOLD}{'═' * 60}{RESET}")
                content = data.get("content", "")
                for line in content.split('\n'):
                    print(f"  {line}")
                print(f"{BOLD}{'═' * 60}{RESET}")

            elif event_type == "observer" and args.verbose and data:
                speaker = data.get("speaker", "")
                summary = data.get("position_summary", "")
                sentiment = data.get("sentiment", {})
                overall = sentiment.get("overall", "N/A") if sentiment else "N/A"
                print(f"{DIM}  [Observer] {speaker}: {summary} (sentiment: {overall}){RESET}")

            elif event_type == "complete":
                status = data.get("status", "complete")
                print(f"\n{BOLD}✓ Session {status}.{RESET}")

            elif event_type == "error":
                error_msg = data.get("message", "Unknown error")
                print(f"\n{BOLD}\033[91m✗ Error: {error_msg}{RESET}")

        # Update session status
        session.status = "complete"
        if engine.round_syntheses:
            session.synthesis = engine.round_syntheses[-1]
        db.commit()

        # Print summary
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        print(f"\n{BOLD}{'═' * 40}{RESET}")
        print(f"{BOLD}  Session Summary{RESET}")
        print(f"{'─' * 40}")
        print(f"  Rounds:     {current_round}")
        print(f"  Turns:      {turn_count}")
        print(f"  Duration:   {minutes}m {seconds}s")
        print(f"  Agents:     {len(stakeholders)} ({args.agents_per_turn} active per turn)")
        print(f"{BOLD}{'═' * 40}{RESET}")

    except KeyboardInterrupt:
        print(f"\n{DIM}Interrupted by user.{RESET}")
        session.status = "stopped"
        db.commit()
    except Exception as e:
        logger.exception("CLI runner error")
        print(f"\n{BOLD}\033[91mFatal error: {e}{RESET}")
        session.status = "failed"
        db.commit()
        sys.exit(1)
    finally:
        db.close()


def _persist_turn(db, session_id, data):
    """Persist a turn message to the DB."""
    from backend.models import Message

    STAGE_MAP = {"intro": 0, "response": 1, "challenge": 2, "synthesis": 3, "inject": 4}
    stage_str = data.get("stage", "response")
    stage_int = STAGE_MAP.get(stage_str, 1)

    try:
        db.add(Message(
            session_id=session_id,
            turn=data.get("turn", 0),
            round_num=data.get("round", 0),
            stage=stage_int,
            speaker=data.get("speaker", ""),
            speaker_name=data.get("speaker_name", ""),
            content=data.get("content", ""),
            finish_reason=data.get("finish_reason"),
        ))
        db.commit()
    except Exception as e:
        logger.error("Failed to persist CLI message: %s", e)


if __name__ == "__main__":
    main()
