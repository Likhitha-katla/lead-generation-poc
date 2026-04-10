class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"{code}: {message}")


class ConfigurationError(Exception):
    pass


class ExternalServiceError(Exception):
    def __init__(self, service_name: str, message: str):
        super().__init__(f"{service_name}: {message}")
