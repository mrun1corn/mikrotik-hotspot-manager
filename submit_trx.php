<?php
require_once __DIR__ . '/vendor/autoload.php';

use RouterOS\Client;
use RouterOS\Query;

// import tg creds
$config = json_decode(file_get_contents(__DIR__ . '/config.json'), true);
$botToken = $config['telegram']['bot_token'];
$chatId = $config['telegram']['admin_chat_id'];

$bkash_number = $_POST['bkash_number'] ?? '';
$trx_id = $_POST['trx_id'] ?? '';
$ip = $_POST['ip'] ?? '';
$package = $_POST['package'] ?? 'unknown';

if ($bkash_number && $trx_id && $ip && $package) {
    try {
        // Generate credentials
        $username = "user" . rand(1000, 9999);
        $password = rand(100000, 999999);
        $comment = "$bkash_number | $trx_id | pending";

        // Connect to MikroTik
        $client = new Client($config['mikrotik']);
        $query = new Query('/ip/hotspot/user/add');
        $query->equal('name', $username)
              ->equal('password', $password)
              ->equal('profile', $package)
              ->equal('disabled', 'yes')
              ->equal('comment', $comment);
        $client->query($query)->read();

		// telegram sendMessage
        $message = "🆕 *New Payment Request:*\n\n"
                 . "📱 *bKash:* `$bkash_number`\n"
                 . "🧾 *Transaction ID:* `$trx_id`\n"
                 . "🌐 *IP:* `$ip`\n"
                 . "📦 *Package:* *" . strtoupper(str_replace("_", " ", $package)) . "*\n"
                 . "👤 *Username:* `$username`\n"
                 . "🔐 *Password:* `$password`";

        $keyboard = [
            'inline_keyboard' => [[
                ['text' => '✅ Approve', 'callback_data' => "approve|$username|$trx_id|$ip|$package"]
            ]]
        ];

        $data = [
            'chat_id' => $chatId,
            'text' => $message,
            'parse_mode' => 'Markdown',
            'reply_markup' => json_encode($keyboard)
        ];

        file_get_contents("https://api.telegram.org/bot$botToken/sendMessage?" . http_build_query($data));

        // Show to user
        echo "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Submitted</title></head><body style='font-family: sans-serif; text-align: center; padding: 50px;'>";
        echo "<h2>✅ Payment Submitted</h2>";
        echo "<p>Your login credentials:</p>";
        echo "<b>Username:</b> <code>$username</code><br>";
        echo "<b>Password:</b> <code>$password</code><br>";
        echo "<p><em>Please wait for admin approval to activate your account.</em></p>";
        echo "<a href='index.php'>Back to Login</a>";
        echo "</body></html>";
    } catch (Exception $e) {
        echo "Error: " . htmlspecialchars($e->getMessage());
    }
} else {
    echo "Missing fields.";
}
