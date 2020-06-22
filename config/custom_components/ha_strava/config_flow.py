"""Config flow for Strava Home Assistant."""
import logging
import asyncio
import aiohttp
import json
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.network import get_url
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, HTTP_OK
import aiohttp
from .const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
    WEBHOOK_SUBSCRIPTION_URL,
    CONF_WEBHOOK_ID,
    CONF_CALLBACK_URL,
)

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

    async def async_step_renew_webhook_subscription(self, data):
        _LOGGER.debug("renew webhook subscription")
        return

    async def async_step_get_oauth_info(self, user_input=None):
        data_schema = {
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_CLIENT_SECRET): str,
        }

        assert self.hass is not None
        if self.hass.config_entries.async_entries(self.DOMAIN):
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            config_entry_oauth2_flow.async_register_implementation(
                self.hass,
                DOMAIN,
                config_entry_oauth2_flow.LocalOAuth2Implementation(
                    self.hass,
                    DOMAIN,
                    user_input[CONF_CLIENT_ID],
                    user_input[CONF_CLIENT_SECRET],
                    OAUTH2_AUTHORIZE,
                    OAUTH2_TOKEN,
                ),
            )
            return await self.async_step_pick_implementation()

        return self.async_show_form(
            step_id="get_oauth_info", data_schema=vol.Schema(data_schema)
        )

    async def async_oauth_create_entry(self, data: dict) -> dict:
        data[
            CONF_CALLBACK_URL
        ] = f"{get_url(self.hass, allow_internal=False, allow_ip=False)}/api/strava/webhook"
        async with aiohttp.ClientSession() as websession:

            post_response = await websession.post(
                url=WEBHOOK_SUBSCRIPTION_URL,
                data={
                    "client_id": self.flow_impl.client_id,
                    "client_secret": self.flow_impl.client_secret,
                    "callback_url": data[CONF_CALLBACK_URL],
                    "verify_token": "HA_STRAVA",
                },
            )
            if post_response.status == 400:
                post_response_content = await post_response.text()

                if "exists" in json.loads(post_response_content)["errors"][0]["code"]:
                    _LOGGER.debug(
                        f"a strava webhook subscription for {data[CONF_CALLBACK_URL]} already exists"
                    )
                else:
                    raise Exception(
                        f"Webhook subscription returned an unexpected response: {post_response_content}"
                    )
            elif post_response.status == 201:
                data[CONF_WEBHOOK_ID] = json.loads(await post_response.text())["id"]
            else:
                _LOGGER.warning(
                    f"unexpected response (status code: {post_response.status}) while creating strava webhook subscription: {await post_response.text()}"
                )
            data[CONF_CLIENT_ID] = self.flow_impl.client_id
            data[CONF_CLIENT_SECRET] = self.flow_impl.client_secret

        return self.async_create_entry(title=self.flow_impl.name, data=data)

    async_step_user = async_step_get_oauth_info

    """
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
    """
