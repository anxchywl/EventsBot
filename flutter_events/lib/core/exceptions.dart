/// Base exception for all API failures. [message] is safe to show to users.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  const ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

/// Thrown on HTTP 401 responses.
class UnauthorizedException extends ApiException {
  const UnauthorizedException(String message) : super(401, message);
}

/// Thrown on HTTP 403 responses.
class ForbiddenException extends ApiException {
  const ForbiddenException(String message) : super(403, message);
}

/// Thrown on HTTP 409 responses.
class ConflictException extends ApiException {
  const ConflictException(String message) : super(409, message);
}
