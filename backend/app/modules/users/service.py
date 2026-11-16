from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.modules.users.schemas import UpdateProfileRequest, UserOut


def to_user_out(user: User) -> UserOut:
    return UserOut(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        user_role=user.user_role,
        created_at=user.created_at,
    )


async def update_profile(db: AsyncSession, user: User, data: UpdateProfileRequest) -> User:
    # Only the display name is mutable; role and email are not accepted by the schema.
    user.display_name = data.display_name
    await db.commit()
    await db.refresh(user)
    return user
