"""The Strava Home Assistant integration."""
import asyncio
import logging
import json
import voluptuous as vol
from aiohttp.web import json_response, Response
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant import data_entry_flow
from aiohttp import ClientSession

from homeassistant.helpers.network import get_url

AUTH_CALLBACK_PATH = "/auth/external/callback"

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    HTTP_OK,
    CONF_WEBHOOK_ID,
)
from homeassistant.components.http.view import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    aiohttp_client,
    config_entry_oauth2_flow,
    config_validation as cv,
)

from .config_flow import OAuth2FlowHandler
from .const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
    WEBHOOK_SUBSCRIPTION_URL,
    CONF_CALLBACK_URL,
)

_LOGGER = logging.getLogger(__name__)

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
# PLATFORMS = ["sensor"]
PLATFORMS = []


async def async_setup(hass: HomeAssistant, config: dict):
    """
    Set up the Strava Home Assistant component.
    """

    if DOMAIN not in config:
        return True

    subscribe_view = StravaSubscribeView()
    hass.http.register_view(subscribe_view)

    existing_config_entry = hass.config_entries.async_entries(DOMAIN)

    if len(existing_config_entry) == 1:
        _LOGGER.debug(f"existing config entry: {existing_config_entry[0].data}")
        OAuth2FlowHandler.async_register_implementation(
            hass,
            config_entry_oauth2_flow.LocalOAuth2Implementation(
                hass,
                DOMAIN,
                existing_config_entry[0].data[CONF_CLIENT_ID],
                existing_config_entry[0].data[CONF_CLIENT_SECRET],
                OAUTH2_AUTHORIZE,
                OAUTH2_TOKEN,
            ),
        )
    return True


async def renew_webhook_subscription(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.info("renewing webhook subscription for HA Strava")
    config_data = {key: value for key, value in entry.data.items()}

    config_data[
        CONF_CALLBACK_URL
    ] = f"{get_url(hass, allow_internal=False, allow_ip=False)}/api/strava/webhook"

    _LOGGER.debug(f"Config data: {config_data}")

    async with ClientSession() as websession:
        callback_response = await websession.get(url=config_data[CONF_CALLBACK_URL])

        if callback_response.status != 200:
            raise Exception(
                f"HA Callback URL for Strava Webhook not available: {await callback_response.text()}"
            )

        get_response = await websession.get(
            url=WEBHOOK_SUBSCRIPTION_URL,
            params={
                "client_id": entry.data[CONF_CLIENT_ID],
                "client_secret": entry.data[CONF_CLIENT_SECRET],
            },
        )

        get_response_content = json.loads(await get_response.text())[0]
        config_data[CONF_WEBHOOK_ID] = get_response_content["id"]
        _STRAVA_CALLBACK_URL = get_response_content["callback_url"]

        _LOGGER.debug(f"Subscription ID: {config_data[CONF_WEBHOOK_ID]}")
        if _STRAVA_CALLBACK_URL != config_data[CONF_CALLBACK_URL]:
            delete_response = await websession.delete(
                url=WEBHOOK_SUBSCRIPTION_URL + f"/{config_data[CONF_WEBHOOK_ID]}",
                data={
                    "client_id": config_data[CONF_CLIENT_ID],
                    "client_secret": config_data[CONF_CLIENT_SECRET],
                },
            )

            if delete_response.status == 204:
                _LOGGER.info("Successfully Deleted Old Subscription")
                post_response = await websession.post(
                    url=WEBHOOK_SUBSCRIPTION_URL,
                    data={
                        "client_id": entry.data[CONF_CLIENT_ID],
                        "client_secret": entry.data[CONF_CLIENT_SECRET],
                        "callback_url": config_data[CONF_CALLBACK_URL],
                        "verify_token": "HA_STRAVA",
                    },
                )
                _LOGGER.debug(f"second post response:{await post_response.text()}")
            else:
                raise Exception(
                    f"Webhook Subscription could not be deleted: {await delete_response.text()}"
                )
        else:
            _LOGGER.info(
                f"There was already a strava webhook subscription for {config_data[CONF_CALLBACK_URL]}"
            )

    _LOGGER.debug(f"new config data: {config_data}")
    hass.config_entries.async_update_entry(entry=entry, data=config_data)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """
    Set up Strava Home Assistant from a config entry.
    This function is called every time the system reboots
    """
    _LOGGER.debug("called async setup entry")
    # print(f"hass implementation data from __init__.py: {hass.data['oauth2_impl']}")
    try:
        implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    except KeyError:
        _LOGGER.warning("HA Strava Component hasn't been set up in the UI")
        return True

    _LOGGER.debug("ha_strava found a valid OAuth implementation")

    # figure out whether the HA url has changed since the most recent reboot; If that's the case, the webhook subscription must be renewed

    """
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "renew_webhook_subscription"},
            data={"id": "dummy_data"},
        )
    )
    """

    def ha_start_handler(event):
        hass.async_create_task(renew_webhook_subscription(hass=hass, entry=entry))

    def core_config_update_handler(event):
        _LOGGER.debug(f"Core config update: {'external_url' in event.data.keys()}")
        hass.async_create_task(renew_webhook_subscription(hass=hass, entry=entry))

    hass.bus.async_listen("homeassistant_start", ha_start_handler)
    hass.bus.async_listen("core_config_updated", core_config_update_handler)

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    _LOGGER.debug("ha_strava has created a running OAuth session")

    await session.async_ensure_token_valid()

    _LOGGER.debug("ha_strava has ensured that the token is valid")

    _LOGGER.debug(f"ha_strava token:{session.token}")

    strava_webhook_view = StravaWebhookView(websession=session)
    hass.http.register_view(strava_webhook_view)

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug(f"Unloading Strava Home Assistant entry: {entry.data}")

    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )

    async with ClientSession() as websession:
        # delete strava webhook subscription
        delete_response = await websession.delete(
            url=WEBHOOK_SUBSCRIPTION_URL + f"/{entry.data[CONF_WEBHOOK_ID]}",
            data={
                "client_id": entry.data[CONF_CLIENT_ID],
                "client_secret": entry.data[CONF_CLIENT_SECRET],
            },
        )

        if delete_response.status == 204:
            _LOGGER.info(
                f"Successfully deleted strava webhook subscription for {entry.data[CONF_CALLBACK_URL]}"
            )
        else:
            _LOGGER.warn(
                f"Strava webhook for {entry.data[CONF_CALLBACK_URL]} could not be deleted: {await delete_response.text()}"
            )

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    _LOGGER.debug(f"Unload OK?: {unload_ok}")

    if unload_ok:
        del implementation
        del entry

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

    def __init__(self, websession):
        """Init the view."""
        self.websession = websession

    async def post(self, request):
        data = await request.json()
        print(type(data))
        print(data)
        activities_response = await self.websession.async_request(
            method="GET",
            url="https://www.strava.com/api/v3/athlete/activities?per_page=5",
        )
        print(f"response status: {activities_response.status}")
        print(f"response content: {await activities_response.text()}")
        return Response(status=HTTP_OK)
