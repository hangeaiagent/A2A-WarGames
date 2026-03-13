"""Apply RLS policies to all tables in Supabase."""
from .database import SessionLocal
from sqlalchemy import text

STATEMENTS = [
    # Enable RLS on all tables
    "ALTER TABLE projects ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE stakeholders ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE stakeholder_edges ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sessions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE analytics_snapshots ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE session_config ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE turn_analytics ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE llm_settings ENABLE ROW LEVEL SECURITY",

    # Projects: owner or public
    """CREATE POLICY projects_select ON projects FOR SELECT
       USING (is_public = true OR user_id::text = current_setting('app.user_id', true))""",
    """CREATE POLICY projects_insert ON projects FOR INSERT
       WITH CHECK (user_id::text = current_setting('app.user_id', true) OR user_id IS NULL)""",
    """CREATE POLICY projects_update ON projects FOR UPDATE
       USING (user_id::text = current_setting('app.user_id', true) OR user_id IS NULL)""",
    """CREATE POLICY projects_delete ON projects FOR DELETE
       USING (user_id::text = current_setting('app.user_id', true))""",

    # LLM Settings: owner only (or null = shared)
    """CREATE POLICY llm_settings_select ON llm_settings FOR SELECT
       USING (user_id::text = current_setting('app.user_id', true) OR user_id IS NULL)""",
    """CREATE POLICY llm_settings_insert ON llm_settings FOR INSERT
       WITH CHECK (user_id::text = current_setting('app.user_id', true) OR user_id IS NULL)""",
    """CREATE POLICY llm_settings_update ON llm_settings FOR UPDATE
       USING (user_id::text = current_setting('app.user_id', true) OR user_id IS NULL)""",

    # Stakeholders: via project ownership
    """CREATE POLICY stakeholders_select ON stakeholders FOR SELECT
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholders.project_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY stakeholders_insert ON stakeholders FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholders.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
    """CREATE POLICY stakeholders_update ON stakeholders FOR UPDATE
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholders.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
    """CREATE POLICY stakeholders_delete ON stakeholders FOR DELETE
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholders.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",

    # Stakeholder Edges: via project ownership
    """CREATE POLICY edges_select ON stakeholder_edges FOR SELECT
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholder_edges.project_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY edges_insert ON stakeholder_edges FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholder_edges.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
    """CREATE POLICY edges_update ON stakeholder_edges FOR UPDATE
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = stakeholder_edges.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",

    # Sessions: via project ownership
    """CREATE POLICY sessions_select ON sessions FOR SELECT
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = sessions.project_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY sessions_insert ON sessions FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM projects WHERE projects.id = sessions.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
    """CREATE POLICY sessions_update ON sessions FOR UPDATE
       USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = sessions.project_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",

    # Messages: via session -> project
    """CREATE POLICY messages_select ON messages FOR SELECT
       USING (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = messages.session_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY messages_insert ON messages FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = messages.session_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
    """CREATE POLICY messages_update ON messages FOR UPDATE
       USING (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = messages.session_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",

    # Analytics Snapshots: via session -> project
    """CREATE POLICY analytics_select ON analytics_snapshots FOR SELECT
       USING (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = analytics_snapshots.session_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY analytics_insert ON analytics_snapshots FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = analytics_snapshots.session_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",

    # Session Config: via session -> project
    """CREATE POLICY session_config_select ON session_config FOR SELECT
       USING (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = session_config.session_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY session_config_insert ON session_config FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = session_config.session_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
    """CREATE POLICY session_config_update ON session_config FOR UPDATE
       USING (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = session_config.session_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",

    # Turn Analytics: via session -> project
    """CREATE POLICY turn_analytics_select ON turn_analytics FOR SELECT
       USING (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = turn_analytics.session_id
         AND (projects.is_public = true OR projects.user_id::text = current_setting('app.user_id', true))))""",
    """CREATE POLICY turn_analytics_insert ON turn_analytics FOR INSERT
       WITH CHECK (EXISTS (SELECT 1 FROM sessions JOIN projects ON projects.id = sessions.project_id
         WHERE sessions.id = turn_analytics.session_id
         AND (projects.user_id::text = current_setting('app.user_id', true) OR projects.user_id IS NULL)))""",
]


def main():
    db = SessionLocal()
    ok = 0
    errors = 0
    for stmt in STATEMENTS:
        try:
            db.execute(text(stmt))
            db.commit()
            ok += 1
        except Exception as e:
            db.rollback()
            err_msg = str(e).split("\n")[0]
            print(f"ERROR: {err_msg}")
            print(f"  SQL: {stmt[:80]}...")
            errors += 1
    db.close()
    print(f"\nDone: {ok} succeeded, {errors} failed")


if __name__ == "__main__":
    main()
