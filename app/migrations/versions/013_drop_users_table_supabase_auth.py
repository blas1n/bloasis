"""Drop users table — auth moved to Supabase.

Revision ID: 013
Revises: 012
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop FK constraint from user_preferences → users
    op.drop_constraint(
        "user_preferences_user_id_fkey",
        "user_preferences",
        schema="user_data",
        type_="foreignkey",
    )

    # 2. Drop users-related objects
    op.drop_index("idx_users_email", table_name="users", schema="user_data")
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON user_data.users")
    op.drop_table("users", schema="user_data")


def downgrade() -> None:
    # Recreate users table
    op.execute("""
        CREATE TABLE user_data.users (
            user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.create_index("idx_users_email", "users", ["email"], schema="user_data")

    # Restore FK constraint
    op.create_foreign_key(
        "user_preferences_user_id_fkey",
        "user_preferences",
        "users",
        ["user_id"],
        ["user_id"],
        source_schema="user_data",
        referent_schema="user_data",
        ondelete="CASCADE",
    )

    # Restore trigger
    op.execute("""
        CREATE TRIGGER update_users_updated_at
            BEFORE UPDATE ON user_data.users
            FOR EACH ROW
            EXECUTE FUNCTION user_data.update_updated_at_column()
    """)
