"""Use the requesting session's configured AstrBot chat provider."""

from ...features.kb.assessment import SYSTEM_PROMPT


def session_commentator(context, origin):
    async def generate(prompt):
        provider_id = await context.get_current_chat_provider_id(origin)
        response = await context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
        )
        return response.completion_text

    return generate
