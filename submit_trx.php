<?php
require_once __DIR__ . '/vendor/autoload.php';

use RouterOS\Client;
use RouterOS\Query;

// Set UTF-8 headers
header('Content-Type: text/html; charset=UTF-8');

// Set time zone to match MikroTik
date_default_timezone_set('Asia/Dhaka');

// Load config
$config = json_decode(file_get_contents(__DIR__ . '/config.json'), true);
$botToken = $config['telegram']['bot_token'];
$chatId = $config['telegram']['admin_chat_id'];
$mikrotikConfig = $config['mikrotik'];

// Valid packages (must match MikroTik profiles and bot.py get_expiry keys)
$validPackages = ['1_day', '7_days', '30_days'];

// Detect client IP (for reference, but not enforced during testing)
function get_client_ip($mikrotikConfig) {
    $ip = 'unknown';
    $private_ip_ranges = [
        '10.0.0.0/8',
        '172.16.0.0/12',
        '192.168.0.0/16'
    ];

    // Log all relevant headers
    $ip_headers = [
        'REMOTE_ADDR',
        'HTTP_X_FORWARDED_FOR',
        'HTTP_X_FORWARDED',
        'HTTP_FORWARDED_FOR',
        'HTTP_FORWARDED',
        'HTTP_CLIENT_IP',
        'HTTP_MIKROTIK_ESP',
        'HTTP_X_MAC_ADDRESS',
    ];
    $headers = array_intersect_key($_SERVER, array_flip($ip_headers));
    error_log("IP detection headers: " . json_encode($headers));

    // Check REMOTE_ADDR first
    if (!empty($_SERVER['REMOTE_ADDR']) && $_SERVER['REMOTE_ADDR'] !== '127.0.0.1') {
        $ip = trim($_SERVER['REMOTE_ADDR']);
        foreach ($private_ip_ranges as $range) {
            $range_parts = explode('/', $range);
            $range_ip = $range_parts[0];
            $mask = $range_parts[1];
            $ip_long = ip2long($ip);
            $range_long = ip2long($range_ip);
            $mask_long = ~((1 << (32 - $mask)) - 1);
            if (($ip_long & $mask_long) === ($range_long & $mask_long)) {
                error_log("Found private IP in REMOTE_ADDR: $ip");
                return $ip;
            }
        }
    }

    // Fallback to DHCP lease query using MAC address
    if (isset($_SERVER['HTTP_X_MAC_ADDRESS']) && $_SERVER['HTTP_X_MAC_ADDRESS']) {
        try {
            $client = new Client($mikrotikConfig);
            $mac = trim($_SERVER['HTTP_X_MAC_ADDRESS']);
            $query = (new Query('/ip/dhcp-server/lease/print'))
                ->where('mac-address', $mac);
            $leases = $client->query($query)->read();
            if (!empty($leases[0]['address'])) {
                $ip = $leases[0]['address'];
                error_log("Found IP from DHCP lease for MAC $mac: $ip");
                return $ip;
            }
            error_log("No DHCP lease found for MAC: $mac");
        } catch (Exception $e) {
            error_log("DHCP query failed: " . $e->getMessage());
        }
    }

    // Check other headers
    foreach (array_diff($ip_headers, ['REMOTE_ADDR', 'HTTP_X_MAC_ADDRESS']) as $header) {
        if (!empty($_SERVER[$header])) {
            $ip_list = explode(',', $_SERVER[$header]);
            $ip = trim($ip_list[0]);
            if (filter_var($ip, FILTER_VALIDATE_IP) && $ip !== '127.0.0.1') {
                foreach ($private_ip_ranges as $range) {
                    $range_parts = explode('/', $range);
                    $range_ip = $range_parts[0];
                    $mask = $range_parts[1];
                    $ip_long = ip2long($ip);
                    $range_long = ip2long($range_ip);
                    $mask_long = ~((1 << (32 - $mask)) - 1);
                    if (($ip_long & $mask_long) === ($range_long & $mask_long)) {
                        error_log("Found private IP in $header: $ip");
                        return $ip;
                    }
                }
            }
        }
    }

    error_log("No valid private IP found, returning invalid");
    return 'invalid';
}

// Calculate validity period (matches bot.py get_expiry)
function get_validity($package) {
    $durations = [
        '1_day' => 1,
        '7_days' => 7,
        '30_days' => 30
    ];
    $days = $durations[$package] ?? 1;
    $validity_time = (new DateTime())->modify("+$days days");
    return $validity_time->format('Y-m-d H:i');
}

// Generate image with user credentials
function generate_credentials_image($username, $password, $package, $validity, $ip) {
    $width = 600;
    $height = 400;
    $image = imagecreatetruecolor($width, $height);

    // Colors
    $white = imagecolorallocate($image, 255, 255, 255);
    $black = imagecolorallocate($image, 0, 0, 0);
    $blue = imagecolorallocate($image, 59, 130, 246);
    $gray = imagecolorallocate($image, 107, 114, 128);

    // Background
    imagefill($image, 0, 0, $white);

    // Load font
    $font = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';
    if (!file_exists($font)) {
        error_log("Font not found: $font. Using default GD font.");
        $font = 5;
    }

    // Title
    $title = "Hotspot Credentials";
    $bbox = imagettfbbox(24, 0, $font, $title);
    $title_width = $bbox[2] - $bbox[0];
    imagettftext($image, 24, 0, ($width - $title_width) / 2, 60, $blue, $font, $title);

    // Details
    $details = [
        "Username: $username",
        "Password: $password",
        "Package: " . str_replace("_", " ", $package),
        "IP: " . ($ip === '0.0.0.0' ? 'Pending' : $ip),
        "Valid Until: $validity"
    ];
    $y = 120;
    foreach ($details as $text) {
        $bbox = imagettfbbox(18, 0, $font, $text);
        $text_width = $bbox[2] - $bbox[0];
        imagettftext($image, 18, 0, ($width - $text_width) / 2, $y, $black, $font, $text);
        $y += 50;
    }

    // Footer
    $footer = "Pending admin approval";
    $bbox = imagettfbbox(14, 0, $font, $footer);
    $footer_width = $bbox[2] - $bbox[0];
    imagettftext($image, 14, 0, ($width - $footer_width) / 2, $height - 30, $gray, $font, $footer);

    // Save image
    $downloads_dir = __DIR__ . '/downloads';
    if (!is_dir($downloads_dir)) {
        if (!mkdir($downloads_dir, 0777, true)) {
            throw new Exception("Failed to create downloads directory at $downloads_dir");
        }
    }
    $image_path = "$downloads_dir/credentials_$username.png";
    imagepng($image, $image_path);
    imagedestroy($image);

    return $image_path;
}

// Form inputs
$bkash_number = $_POST['bkash_number'] ?? '';
$package = $_POST['package'] ?? '';
$proof_image = $_FILES['proof_image'] ?? null;

// Override POST IP with detected IP
$ip = get_client_ip($mikrotikConfig);
error_log("Overriding POST IP with detected IP: $ip");

// Temporarily bypass IP validation for testing
if ($ip === 'invalid') {
    $ip = '0.0.0.0'; // Placeholder for testing
    error_log("Using placeholder IP 0.0.0.0 for testing");
}

error_log("Final inputs: bkash_number=$bkash_number, ip=$ip, package=$package");

if ($bkash_number && $package && in_array($package, $validPackages) && $proof_image && $proof_image['error'] === UPLOAD_ERR_OK) {
    try {
        // Validate image
        $allowed_types = ['image/jpeg', 'image/png', 'image/gif'];
        if (!in_array($proof_image['type'], $allowed_types)) {
            throw new Exception("Invalid image format. Only JPEG, PNG, or GIF allowed.");
        }
        if ($proof_image['size'] > 5 * 1024 * 1024) { // 5MB limit
            throw new Exception("Image file size exceeds 5MB limit.");
        }

        // Generate credentials
        $username = "user" . rand(1000, 9999);
        $password = rand(100000, 999999);
        $comment = "$bkash_number | pending";
        $validity = get_validity($package);

        // Save to file (for bot to enable later)
        $user_data = [
            'username' => $username,
            'password' => (string)$password,
            'ip' => $ip,
            'package' => $package,
            'bkash' => $bkash_number
        ];

        // Create pending_users directory
        error_log("Current directory: " . __DIR__);
        if (!is_dir(__DIR__ . '/pending_users')) {
            if (!mkdir(__DIR__ . '/pending_users', 0777, true)) {
                throw new Exception("Failed to create pending_users directory at " . __DIR__ . '/pending_users');
            }
            error_log("Created pending_users directory: " . __DIR__ . '/pending_users');
        }

        // Write JSON file
        $json_file = __DIR__ . "/pending_users/$username.json";
        if (file_put_contents($json_file, json_encode($user_data)) === false) {
            throw new Exception("Failed to write JSON file for username: $username at $json_file");
        }
        error_log("Wrote JSON file: $json_file");

        // Save proof image
        $proof_dir = __DIR__ . '/proof_images';
        if (!is_dir($proof_dir)) {
            if (!mkdir($proof_dir, 0777, true)) {
                throw new Exception("Failed to create proof_images directory at $proof_dir");
            }
        }
        $proof_path = "$proof_dir/$username." . pathinfo($proof_image['name'], PATHINFO_EXTENSION);
        if (!move_uploaded_file($proof_image['tmp_name'], $proof_path)) {
            throw new Exception("Failed to save proof image for username: $username");
        }
        error_log("Saved proof image: $proof_path");

        // Generate credentials image
        $image_path = generate_credentials_image($username, $password, $package, $validity, $ip);
        $image_url = "downloads/credentials_$username.png";

        // Add disabled user to MikroTik
        $client = new Client($mikrotikConfig);
        $query = (new Query('/ip/hotspot/user/add'))
            ->equal('name', $username)
            ->equal('password', (string)$password)
            ->equal('profile', $package)
            ->equal('disabled', 'yes')
            ->equal('comment', $comment);
        $client->query($query)->read();

        // Send request to bot with image
        $message = "*New Payment Request:*\n\n"
                 . "bKash: `$bkash_number`\n"
                 . "IP: `" . ($ip === '0.0.0.0' ? 'Pending' : $ip) . "`\n"
                 . "Package: `" . strtoupper(str_replace("_", " ", $package)) . "`\n"
                 . "Username: `$username`\n"
                 . "Password: `$password`";

        $keyboard = [
            'inline_keyboard' => [[
                ['text' => 'Approve', 'callback_data' => "approve|$bkash_number|$username|$ip|$package"],
                ['text' => 'Reject', 'callback_data' => "reject|$bkash_number|$username|$ip|$package"]
            ]]
        ];

        $data = [
            'chat_id' => $chatId,
            'caption' => $message,
            'parse_mode' => 'Markdown',
            'reply_markup' => json_encode($keyboard)
        ];

        $ch = curl_init("https://api.telegram.org/bot$botToken/sendPhoto");
        curl_setopt($ch, CURLOPT_POST, 1);
        curl_setopt($ch, CURLOPT_POSTFIELDS, [
            'chat_id' => $chatId,
            'photo' => new CURLFile($proof_path),
            'caption' => $message,
            'parse_mode' => 'Markdown',
            'reply_markup' => json_encode($keyboard)
        ]);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        $telegram_response = curl_exec($ch);
        if ($telegram_response === false) {
            throw new Exception("Failed to send Telegram photo: " . curl_error($ch));
        }
        curl_close($ch);
        error_log("Telegram photo sent: $telegram_response");

        // Output to user
        echo "<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Payment Submitted</title>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <link href='https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css' rel='stylesheet'>
    <link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css' rel='stylesheet'>
</head>
<body class='bg-gray-100 flex items-center justify-center min-h-screen'>
    <div class='bg-white p-8 rounded-lg shadow-lg max-w-md w-full'>
        <h2 class='text-2xl font-bold text-blue-600 text-center mb-6'><i class='fa-solid fa-check-circle mr-2'></i>Payment Submitted</h2>
        <p class='text-gray-600 text-center mb-4'>Your login credentials (pending admin approval):</p>
        <div class='bg-gray-50 p-4 rounded-md mb-6'>
            <p class='text-lg'><strong>Username:</strong> <code>$username</code></p>
            <p class='text-lg'><strong>Password:</strong> <code>$password</code></p>
            <p class='text-lg'><strong>IP:</strong> " . ($ip === '0.0.0.0' ? 'Pending' : $ip) . "</p>
            <p class='text-lg'><strong>Package:</strong> " . str_replace("_", " ", $package) . "</p>
            <p class='text-lg'><strong>Valid Until:</strong> $validity</p>
        </div>
        <div class='text-center mb-6'>
            <a href='$image_url' download='credentials_$username.png' class='inline-block bg-blue-500 text-white font-semibold py-2 px-4 rounded hover:bg-blue-600 transition'>
                <i class='fa-solid fa-download mr-2'></i>Download Credentials
            </a>
        </div>
        <p class='text-gray-500 text-sm text-center italic'>Please wait for admin approval to activate your account.</p>
        <div class='text-center mt-4'>
            <a href='index.php' class='text-blue-500 hover:underline'><i class='fa-solid fa-arrow-left mr-2'></i>Back to Login</a>
        </div>
    </div>
</body>
</html>";
    } catch (Exception $e) {
        error_log("Error in submit_trx.php: " . $e->getMessage());
        echo "<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Error</title>
    <link href='https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css' rel='stylesheet'>
    <link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css' rel='stylesheet'>
</head>
<body class='bg-gray-100 flex items-center justify-center min-h-screen'>
    <div class='bg-white p-8 rounded-lg shadow-lg max-w-md w-full'>
        <h2 class='text-2xl font-bold text-red-600 text-center mb-6'><i class='fa-solid fa-exclamation-circle mr-2'></i>Error</h2>
        <p class='text-gray-600 text-center'>" . htmlspecialchars($e->getMessage()) . "</p>
        <div class='text-center mt-4'>
            <a href='index.php' class='text-blue-500 hover:underline'><i class='fa-solid fa-arrow-left mr-2'></i>Back to Login</a>
        </div>
    </div>
</body>
</html>";
    }
} else {
    $missing_fields = [];
    if (!$bkash_number) $missing_fields[] = 'bkash_number';
    if (!$package || !in_array($package, $validPackages)) $missing_fields[] = 'package';
    if (!$proof_image || $proof_image['error'] !== UPLOAD_ERR_OK) $missing_fields[] = 'proof_image';
    $error_msg = "Missing or invalid fields: " . implode(", ", $missing_fields) . ". Valid packages: " . implode(", ", $validPackages);
    error_log($error_msg);
    echo "<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Error</title>
    <link href='https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css' rel='stylesheet'>
    <link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css' rel='stylesheet'>
</head>
<body class='bg-gray-100 flex items-center justify-center min-h-screen'>
    <div class='bg-white p-8 rounded-lg shadow-lg max-w-md w-full'>
        <h2 class='text-2xl font-bold text-red-600 text-center mb-6'><i class='fa-solid fa-exclamation-circle mr-2'></i>Error</h2>
        <p class='text-gray-600 text-center'>$error_msg</p>
        <div class='text-center mt-4'>
            <a href='index.php' class='text-blue-500 hover:underline'><i class='fa-solid fa-arrow-left mr-2'></i>Back to Login</a>
        </div>
    </div>
</body>
</html>";
}
?>
