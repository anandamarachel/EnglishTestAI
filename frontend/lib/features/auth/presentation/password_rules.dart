/// Password rules the backend enforces (8–256 characters, no composition rules),
/// with the app's Indonesian messages. Passwords are never trimmed.
String? newPasswordError(String password) => password.length < 8
    ? 'Password minimal 8 karakter.'
    : password.length > 256
        ? 'Password maksimal 256 karakter.'
        : null;

String? confirmationError(String confirmation, String password) =>
    confirmation.isEmpty || confirmation != password ? 'Konfirmasi password tidak sama.' : null;

/// When the server rejects the new password (e.g. a stricter deployed policy).
const passwordRuleMessage = 'Password belum memenuhi syarat (8–256 karakter).';
