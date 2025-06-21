<?php
$bkash_number = $_POST['bkash_number'] ?? '';
$trx_id = $_POST['trx_id'] ?? '';
$ip = $_POST['ip'] ?? '';
$package = $_POST['package'] ?? 'unknown';

if ($bkash_number && $trx_id && $ip && $package) {
    $botToken = "";
    $adminChatId = "";

    $message = "ðŸ†• *New Payment Request:*\n\n"
             . "ðŸ“± *bKash:* `$bkash_number`\n"
             . "ðŸ§¾ *Transaction ID:* `$trx_id`\n"
             . "ðŸŒ *IP:* `$ip`\n"
             . "ðŸ“¦ *Package:* *" . strtoupper(str_replace("_", " ", $package)) . "*";

    $inlineKeyboard = [
        'inline_keyboard' => [[
            ['text' => 'âœ… Approve', 'callback_data' => "approve|$bkash_number|$trx_id|$ip|$package"]
        ]]
    ];

    $url = "https://api.telegram.org/bot$botToken/sendMessage";
    $data = [
        'chat_id' => $adminChatId,
        'text' => $message,
        'parse_mode' => 'Markdown',
        'reply_markup' => json_encode($inlineKeyboard)
    ];

    file_get_contents($url . "?" . http_build_query($data));

    echo "<script>
        alert('Submitted! Please wait for admin approval.');
        window.location.href='index.php';
    </script>";
} else {
    echo "Missing fields.";
}
?>
