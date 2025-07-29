from sqlbot_xpack.core import sqlbot_decrypt as xpack_sqlbot_decrypt

async def sqlbot_decrypt(text: str) -> str:
    return await xpack_sqlbot_decrypt(text)