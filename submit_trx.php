<?php
require_once __DIR__ . '/vendor/autoload.php';

use RouterOS\Client;
use RouterOS\Query;

// Load config
$config = json_decode(file_get_contents(__DIR__ . '/config.json'), true);
$botToken = $config['telegram']['bot_token'];
$chatId = $config['telegram']['admin_chat_id'];
$mikrotikConfig = $config['mikrotik'];

// Valid packages (must match MikroTik profiles and bot.py get_expiry keys)
$validPackages = ['1_day', '7_days', '30_days'];

// Form inputs
$bkash_number = $_POST['bkash_number'] ?? '';
$trx_id = $_POST['trx_id'] ?? '';
$ip = $_POST['ip'] ?? '';
$package = $_POST['package'] ?? '';

error_log("Form inputs: bkash_number=$bkash_number, trx_id=$trx_id, ip=$ip, package=$package");

if ($bkash_number && $trx_id && $ip && in_array($package, $validPackages)) {
    try {
        // Validate trx_id for safe filename
        if (!preg_match('/^[a-zA-Z0-9_-]+$/', $trx_id)) {
            throw new Exception("Invalid transaction ID: $trx_id. Use alphanumeric characters, underscores, or hyphens only.");
        }

        // Generate credentials
        $username = "user" . rand(1000, 9999);
        $password = rand(100000, 999999);
        $comment = "$bkash_number | $trx_id | pending";

        // Save to file (for bot to enable later)
        $user_data = [
            'username' => $username,
            'password' => (string)$password, // Ensure string for consistency
            'ip' => $ip,
            'package' => $package,
            'bkash' => $bkash_number
        ];

        // Create pending_users directory if it doesn't exist
        error_log("Current directory: " . __DIR__);
        if (!is_dir(__DIR__ . '/pending_users')) {
            if (!mkdir(__DIR__ . '/pending_users', 0777, true)) {
                throw new Exception("Failed to create pending_users directory at " . __DIR__ . '/pending_users');
            }
            error_log("Created pending_users directory: " . __DIR__ . '/pending_users');
        }

        // Write JSON file
        $json_file = __DIR__ . "/pending_users/$trx_id.json";
        if (file_put_contents($json_file, json_encode($user_data)) === false) {
            throw new Exception("Failed to write JSON file for trx_id: $trx_id at $json_file");
        }
        error_log("Wrote JSON file: $json_file");

        // Add disabled user to MikroTik
        $client = new Client($mikrotikConfig);
        $query = (new Query('/ip/hotspot/user/add'))
            ->equal('name', $username)
            ->equal('password', (string)$password) // Ensure string
            ->equal('profile', $package)
            ->equal('disabled', 'yes')
            ->equal('comment', $comment);
        $client->query($query)->read();

        // Send request to bot
        $message = "🔔 *New Payment Request:*\n\n"
                 . "📱 *bKash:* `$bkash_number`\n"
                 . "🔄 *Transaction ID:* `$trx_id`\n"
                 . "🌐 *IP:* `$ip`\n"
                 . "📦 *Package:* `" . strtoupper(str_replace("_", " ", $package)) . "`\n"
                 . "👤 *Username:* `$username`\n"
                 . "🔐 *Password:* `$password`";

        $keyboard = [
            'inline_keyboard' => [[
                ['text' => '✅ Approve', 'callback_data' => "approve|$bkash_number|$trx_id|$ip|$package"]
            ]]
        ];

        $data = [
            'chat_id' => $chatId,
            'text' => $message,
            'parse_mode' => 'Markdown',
            'reply_markup' => json_encode($keyboard)
        ];

        $telegram_response = file_get_contents("https://api.telegram.org/bot$botToken/sendMessage?" . http_build_query($data));
        if ($telegram_response === false) {
            throw new Exception("Failed to send Telegram message");
        }
        error_log("Telegram message sent: $telegram_response");

        // Output to user
        echo "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Submitted</title></head><body style='font-family: sans-serif; text-align: center; padding: 50px;'>";
        echo "<h2>✅ Payment Submitted</h2>";
        echo "<p>Your login credentials (disabled until admin approval):</p>";
        echo "<b>Username:</b> <code>$username</code><br>";
        echo "<b>Password:</b> <code>$password</code><br>";
        echo "<p><em>Please wait for admin approval to activate your account.</em></p>";
        echo "<a href='index.php'>Back to Login</a>";
        echo "</body></html>";
    } catch (Exception $e) {
        error_log("Error in submit_trx.php: " . $e->getMessage());
        echo "Error: " . htmlspecialchars($e->getMessage());
    }
} else {
    $missing_fields = [];
    if (!$bkash_number) $missing_fields[] = 'bkash_number';
    if (!$trx_id) $missing_fields[] = 'trx_id';
    if (!$ip) $missing_fields[] = 'ip';
    if (!in_array($package, $validPackages)) $missing_fields[] = 'package';
    $error_msg = "Missing or invalid fields: " . implode(", ", $missing_fields) . ". Valid packages: " . implode(", ", $validPackages);
    error_log($error_msg);
    echo $error_msg;
}
?>
