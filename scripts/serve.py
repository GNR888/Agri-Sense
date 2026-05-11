"""Development server — runs the Agri-Sense FastAPI app with auto-reload."""

import uvicorn

# Extend uvicorn's default logging config to include the root logger at INFO
# so application-level logger.info() calls (e.g. the request middleware) appear.
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
        "app": {
            "format": "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
        "app": {
            "formatter": "app",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        "agri_sense": {"handlers": ["app"], "level": "INFO", "propagate": False},
    },
}

if __name__ == "__main__":
    uvicorn.run(
        "agri_sense.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=LOG_CONFIG,
    )
