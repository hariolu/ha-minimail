DOMAIN = "minimail"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FOLDER = "folder"
CONF_SSL = "ssl"
CONF_SENDER_FILTERS = "sender_filters"
CONF_SEARCH = "search"
CONF_FETCH_LIMIT = "fetch_limit"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_PORT = 993
DEFAULT_SSL = True
DEFAULT_FOLDER = "INBOX"
DEFAULT_FETCH_LIMIT = 25
DEFAULT_UPDATE_INTERVAL = 120
DEFAULT_SEARCH = "ALL"

DEVICE_NAME = "minimail"     
ENTITY_PREFIX = "minimail"   

# Persistent cache (Store) config
STORAGE_KEY = f"{DOMAIN}_cache"
STORAGE_VERSION = 1