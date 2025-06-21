<?php
$bkash_number = $_POST['bkash_number'] ?? '';
$trx_id = $_POST['trx_id'] ?? '';
$ip = $_POST['ip'] ?? '';
$package = $_POST['package'] ?? 'unknown';

if ($bkash_number && $trx_id && $ip && $package) {
    $botToken = "";      
    $adminChatId = "";   

    $safe_package = strtoupper(str_replace("_", " ", $package));
    $message = "📬 *New Payment Request:*\n\n"
             . "📱 *bKash:* `" . addslashes($bkash_number) . "`\n"
             . "🧾 *Transaction ID:* `" . addslashes($trx_id) . "`\n"
             . "🌐 *IP:* `" . addslashes($ip) . "`\n"
             . "📦 *Package:* *" . addslashes($safe_package) . "*";

    // Inline keyboard with callback data
    $inlineKeyboard = [
        'inline_keyboard' => [[
            ['text' => '✅ Approve', 'callback_data' => "approve|$bkash_number|$trx_id|$ip|$package"]
        ]]
    ];

    $url = "https://api.telegram.org/bot$botToken/sendMessage";
    $data = [
        'chat_id' => $adminChatId,
        'text' => $message,
        'parse_mode' => 'Markdown',
        'reply_markup' => json_encode($inlineKeyboard)
    ];

    // Send message to admin
    file_get_contents($url . "?" . http_build_query($data));

    echo "<script>
        alert('Submitted! Please wait for admin approval.');
        window.location.href='index.php';
    </script>";
} else {
    echo "Missing fields.";
}
?>
