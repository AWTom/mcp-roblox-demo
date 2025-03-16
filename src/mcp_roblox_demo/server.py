import asyncio
import httpx
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field


# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("mcp-roblox-demo")

# Set dependencies for deployment
mcp.dependencies = ["python-dotenv>=0.20.0"]

# Constants for Roblox Open Cloud API
ROBLOX_API_BASE = "https://apis.roblox.com/cloud/v2"


class ScriptPatchRequest(BaseModel):
    script_content: str = Field(...,
                                description="Only the contents of a Roblox Lua file")


async def make_roblox_request(
    api_key: str, method: str, url: str, data: dict | None = None, is_polling: bool = False
) -> dict[str, Any] | None:
    """Make a request to the Roblox Open Cloud API with proper error handling."""
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, timeout=30.0)
            elif method.upper() == "PATCH":
                response = await client.patch(
                    url, headers=headers, json=data, timeout=30.0
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            # Always expect a JSON response
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Roblox API Error: {
                  e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            print(f"Error making Roblox API request: {e}")
            return None


async def poll_for_results(api_key: str, operation_path: str, retries: int = 10, delay: int = 5) -> dict | None:
    """Polls the Roblox API for the operation's completion status."""
    url = f"{ROBLOX_API_BASE}/{operation_path}"
    for _ in range(retries):
        # Corrected to pass is_polling
        response_data = await make_roblox_request(api_key, "GET", url, is_polling=True)
        if response_data and response_data.get("done"):
            return response_data
        await asyncio.sleep(delay)
    return None


@mcp.tool()
async def update_script(
    universe_id: int,
    place_id: int,
    instance_id: str,
    script_content: str,
) -> str:
    """Updates a Roblox script instance using a PATCH request and polls for completion.

    Args:
        universe_id: The ID of the Roblox universe.
        place_id: The ID of the Roblox place within the universe.
        instance_id: The ID of the script instance to update.
        script_content: The new Lua code for the script.
    """
    api_key = os.getenv("ROBLOX_API_KEY")
    if not api_key:
        return "Error: Roblox Open Cloud API Key is required."

    # Construct URL. Instance IDs are strings.
    url = f"{
        ROBLOX_API_BASE}/universes/{universe_id}/places/{place_id}/instances/{instance_id}"

    # Prepare the PATCH data.  Roblox expects a full replacement, so we provide all fields.  Crucially, 'className' needs to be sent.
    patch_data = {
        "engineInstance": {
            "Details": {
                "Script": {  # TODO edit this to handle ModuleScript and LocalScript
                    "Source": script_content
                }
            }
        }
    }

    # Make the PATCH request
    patch_response = await make_roblox_request(api_key, "PATCH", url, data=patch_data)

    if patch_response is None:
        return "Error: Failed to initiate script update."

    # Check for and handle the operation path
    operation_path = patch_response.get("path")
    if not operation_path:
        return "Error: Operation path not found in PATCH response."

    # Poll for the operation's completion
    poll_result = await poll_for_results(api_key, operation_path)

    if poll_result:
        if poll_result.get("done"):
            # Check for successful response within the polling result
            if "response" in poll_result:
                return f"Script updated successfully! Final Response: {poll_result['response']}"
            elif "error" in poll_result:  # Check for an error
                return f"Script update failed. Error: {poll_result['error']}"
            else:  # If neither response nor error
                return "Script update operation completed, but no response data found."
        else:
            return "Script update operation did not complete within the allowed time."
    else:
        return "Error: Failed to poll for script update status."


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
