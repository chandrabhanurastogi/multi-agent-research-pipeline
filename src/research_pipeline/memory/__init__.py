"""Memory: persisting run state. There is no cross-run memory.

    audit.py   save RunState to runs/<run_id>.json
                         (production: checkpoint store; long-term memory would also live here)
"""
