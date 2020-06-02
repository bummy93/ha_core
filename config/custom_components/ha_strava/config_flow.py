"""Config flow for Strava Home Assistant."""
import logging
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.network import get_url
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, HTTP_OK
import aiohttp
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Strava Home Assistant OAuth2 authentication."""

    DOMAIN = DOMAIN
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_PUSH

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": "activity:read",
            "approval_prompt": "force",
            "response_type": "code",
        }

    async def async_oauth_create_entry(self, data: dict) -> dict:
        print(f"oauth data: {data}")
        async with aiohttp.ClientSession() as session:
            payload = {
                "client_id": "46186",
                "client_secret": "6b3d8c8ab29664583925d2c93b1c12c2e0a21c78",
                "callback_url": "http://9548b6f228ed.ngrok.io/api/strava/webhook",
                "verify_token": "HA_STRAVA",
            }

            request_url = "https://www.strava.com/api/v3/push_subscriptions"

            async with session.post(url=request_url, data=payload) as resp:
                print(resp.status)
                print(await resp.text())

        return self.async_create_entry(title="Strava Home Assistant", data=data)

    async def async_step_import(self, config):
        _LOGGER.debug("async step init")
        _LOGGER.debug(f"config: {config}")
        await asyncio.sleep(10)
        request_url = "https://www.strava.com/api/v3/push_subscriptions"
        CALLBACK_URL = f"{config['hass_url']}/api/strava/webhook"
        payload = {
            "client_id": config[DOMAIN][CONF_CLIENT_ID],
            "client_secret": config[DOMAIN][CONF_CLIENT_SECRET],
            "callback_url": CALLBACK_URL,
            "verify_token": "HA_STRAVA",
        }

        _LOGGER.debug(f"callback url:{CALLBACK_URL}")
        async with aiohttp.ClientSession() as websession:
            post_response = await websession.post(url=request_url, data=payload)
        _LOGGER.debug("did we get here?")
        _LOGGER.debug(f"initial post response:{await post_response.text()}")
        _LOGGER.debug(f"callback_url: {CALLBACK_URL}")

        return self.async_create_entry(title="Strava Webhook", data={})
