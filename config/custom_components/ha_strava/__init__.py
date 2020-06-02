"""The Strava Home Assistant integration."""
import asyncio
import logging
import json
import voluptuous as vol
from aiohttp.web import json_response, Response
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiohttp import MultipartWriter

from homeassistant.helpers.network import get_url

AUTH_CALLBACK_PATH = "/auth/external/callback"

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, HTTP_OK
from homeassistant.components.http.view import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    aiohttp_client,
    config_entry_oauth2_flow,
    config_validation as cv,
)

from .config_flow import OAuth2FlowHandler
from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID): cv.string,
                vol.Required(CONF_CLIENT_SECRET): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
# PLATFORMS = ["sensor"]
PLATFORMS = []


async def async_setup(hass: HomeAssistant, config: dict):
    """
    Set up the Strava Home Assistant component.
    This function is only called once upon the installation of the integration
    """

    _LOGGER.debug("called async setup")

    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    subscribe_view = StravaSubscribeView()
    hass.http.register_view(subscribe_view)

    """
    if post_response.status == 400:
        post_response_content = await post_response.text()

        if "exists" in json.loads(post_response_content)["errors"][0]["code"]:
            _LOGGER.debug("get all the details")
            params = {
                "client_id": config[DOMAIN][CONF_CLIENT_ID],
                "client_secret": config[DOMAIN][CONF_CLIENT_SECRET],
            }

            get_response = await websession.get(url=request_url, params=params)

            get_response_content = json.loads(await get_response.text())[0]
            webhook_id = get_response_content["id"]
            callback_url = get_response_content["callback_url"]

            if callback_url != CALLBACK_URL:
                _LOGGER.info("Updating callback URL for strava webhook")

                delete_response = await websession.delete(
                    url=request_url + f"/{webhook_id}", data=params
                )
                if delete_response.status == 204:
                    _LOGGER.info("Successfully Deleted Old Subscription")
                    post_response = await websession.post(url=request_url, data=payload)
                    _LOGGER.debug(f"second post response:{post_response.text()}")
                else:
                    raise Exception("Webhook Subscription could not be deleted")
            else:
                _LOGGER.info(
                    f"Strava Webhook subscription for {CALLBACK_URL} already existed"
                )
        else:
            raise Exception(
                f"Webhook subscription returned an unexpected response: {post_response_content}"
            )

            # if the callback URL has changed, create a new subscription
    """
    OAuth2FlowHandler.async_register_implementation(
        hass,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass,
            DOMAIN,
            config[DOMAIN][CONF_CLIENT_ID],
            config[DOMAIN][CONF_CLIENT_SECRET],
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        ),
    )

    hass.data[DOMAIN] = config
    """
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=config
        )
    )
    """
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """
    Set up Strava Home Assistant from a config entry.
    This function is called every time the system reboots
    """
    _LOGGER.debug("called async setup entry")
    config = hass.data[DOMAIN]
    try:
        implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    except KeyError:
        _LOGGER.warning("HA Strava Component hasn't been set up in the UI")
        return True

    _LOGGER.debug("ha_strava found a valid OAuth implementation")

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    _LOGGER.debug("ha_strava has created a running OAuth session")

    await session.async_ensure_token_valid()

    _LOGGER.debug("ha_strava has ensured that the token is valid")

    _LOGGER.debug(f"ha_strava token:{session.token}")

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    # if unload_ok:
    #    hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class StravaOAuth2Imlementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    @property
    def redirect_uri(self) -> str:
        """Return the redirect uri."""
        return f"{get_url(self.hass, allow_internal=False, allow_ip=False)}{AUTH_CALLBACK_PATH}"


class StravaSubscribeView(HomeAssistantView):
    url = "/api/strava/webhook"
    name = "api:strava:webhook"
    requires_auth = False
    cors_allowed = True

    def __init__(self):
        """Init the view."""
        pass

    async def get(self, request):
        print("handling get request")
        """Handle the incoming webhook challenge"""
        webhook_subscription_challenge = request.query.get("hub.challenge", None)
        print(f"webhook subscription challenge: {(webhook_subscription_challenge)}")
        if webhook_subscription_challenge:
            return json_response(
                status=HTTP_OK, data={"hub.challenge": webhook_subscription_challenge}
            )

        return Response(status=HTTP_OK)


class StravaWebhookView(HomeAssistantView):
    url = "/api/strava/webhook"
    name = "api:strava:webhook"
    requires_auth = False
    cors_allowed = True

    def __init__(self):
        """Init the view."""
        pass

    async def post(self, request):
        data = await request.json()
        print(type(data))
        print(data)
        return Response(status=HTTP_OK)
