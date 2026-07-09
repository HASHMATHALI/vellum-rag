import logging
import asyncio
from typing import List, Dict, AsyncGenerator
from groq import AsyncGroq
from app.config.settings import settings

logger = logging.getLogger(__name__)

class GroqClient:
    """Interface to connect to Groq Cloud API for fast LLM inference (Llama-3.3-70B-Versatile)."""
    
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        if self.api_key:
            self.client = AsyncGroq(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("GroqClient: GROQ_API_KEY is not configured. Running in Mock fallback mode.")

    async def stream_chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        """Streams LLM chat completions chunk-by-chunk."""
        if self.client:
            try:
                # Call Groq API
                completion = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True
                )
                
                async for chunk in completion:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
            except Exception as e:
                logger.error(f"GroqClient: API call failed ({e}). Yielding fallback message.")
                yield f"\n\n*(Error communicating with Groq API: {e})*\n\n"
        else:
            # Mock LLM response generator for testing when API key is missing
            yield "### [Dry Run/Mock Mode Activated]\n\n"
            yield "It looks like your **GROQ_API_KEY** is not configured. Here is a simulated response based on the search context:\n\n"
            
            mock_response = (
                "Based on the documents you provided, the system retrieved relevant sections to answer your query. "
                "The documents contain information regarding your search. If you configure a valid API key, the system "
                "will invoke the Llama-3.3-70B model to generate a precise answer with file citations. "
                "Please configure `GROQ_API_KEY` in your `.env` file to enable real answers.\n\n"
                "Here are some actions you can take:\n"
                "- Upload files on the **Dashboard**.\n"
                "- Query documents with different search settings (MMR, Hybrid).\n"
                "- View user and query statistics on the **Admin Panel**."
            )
            for chunk in mock_response.split(" "):
                yield chunk + " "
                await asyncio.sleep(0.04)

    async def generate_chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: str = "llama-3.3-70b-versatile"
    ) -> str:
        """Non-streaming chat completion for helper operations (like query reformulation)."""
        if self.client:
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=256
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"GroqClient: API call failed ({e})")
                return ""
        else:
            # Return last message content as fallback query
            user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return user_msg

# Instantiate global Groq client
groq_client = GroqClient()
