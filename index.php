<?php
require_once __DIR__ . '/vendor/autoload.php';

use RouterOS\Client;
use RouterOS\Query;

session_start();

$config = json_decode(file_get_contents(__DIR__ . '/config.json'), true);

//import creds from config
$mikrotikConfig = $config['mikrotik'];
$mikrotikConfig['host'];
$mikrotikConfig['user'];
$mikrotikConfig['pass'];
$mikrotikConfig['port'];

$error = '';
$userInfo = null;

function formatBytes($bytes, $precision = 2) {
    $units = ['B', 'KB', 'MB', 'GB', 'TB'];
    $bytes = max($bytes, 0);
    $power = floor(($bytes ? log($bytes) : 0) / log(1024));
    return round($bytes / pow(1024, $power), $precision) . ' ' . $units[$power];
}

function formatDuration($duration) {
    $parts = explode(":", $duration);
    if (count($parts) === 3) {
        return "{$parts[0]}h {$parts[1]}m {$parts[2]}s";
    }
    return $duration;
}

// Logout handler
if (isset($_GET['logout'])) {
    session_destroy();
    header("Location: index.php");
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = trim($_POST['username'] ?? '');
    $password = trim($_POST['password'] ?? '');

    if (!$username || !$password) {
        $error = "Please enter both username and password.";
    } else {
        try {
            $client = new Client($mikrotikConfig);

            $queryUser = (new Query('/ip/hotspot/user/print'))->where('name', $username);
            $users = $client->query($queryUser)->read();

            if (count($users) === 0) {
                $error = "User not found.";
            } else {
                $user = $users[0];

                if ($user['password'] !== $password) {
                    $error = "Incorrect password.";
                } else {
                    $_SESSION['username'] = $username;

                    $queryActive = (new Query('/ip/hotspot/active/print'))->where('user', $username);
                    $active = $client->query($queryActive)->read();
                    $session = $active[0] ?? [];

                    $userInfo = [
                        'username' => $username,
                        'profile' => $user['profile'] ?? 'N/A',
                        'uptime' => isset($session['uptime']) ? formatDuration($session['uptime']) : 'Not Connected',
                        'ip' => $session['address'] ?? 'N/A',
                        'mac' => $session['mac-address'] ?? 'N/A',
                        'upload' => isset($session['bytes-out']) ? formatBytes($session['bytes-out']) : '0 B',
                        'download' => isset($session['bytes-in']) ? formatBytes($session['bytes-in']) : '0 B',
                        'remaining_time' => $user['limit-uptime'] ?? 'Unlimited',
                    ];
                }
            }
        } catch (Exception $e) {
            $error = "MikroTik Error: " . $e->getMessage();
        }
    }
} elseif (isset($_SESSION['username'])) {
    try {
        $client = new Client($mikrotikConfig);
        $username = $_SESSION['username'];

        $queryUser = (new Query('/ip/hotspot/user/print'))->where('name', $username);
        $users = $client->query($queryUser)->read();

        if (count($users)) {
            $user = $users[0];
            $queryActive = (new Query('/ip/hotspot/active/print'))->where('user', $username);
            $active = $client->query($queryActive)->read();
            $session = $active[0] ?? [];

            $userInfo = [
                'username' => $username,
                'profile' => $user['profile'] ?? 'N/A',
                'uptime' => isset($session['uptime']) ? formatDuration($session['uptime']) : 'Not Connected',
                'ip' => $session['address'] ?? 'N/A',
                'mac' => $session['mac-address'] ?? 'N/A',
                'upload' => isset($session['bytes-out']) ? formatBytes($session['bytes-out']) : '0 B',
                'download' => isset($session['bytes-in']) ? formatBytes($session['bytes-in']) : '0 B',
                'remaining_time' => $user['limit-uptime'] ?? 'Unlimited',
            ];
        } else {
            session_destroy();
        }
    } catch (Exception $e) {
        $error = "MikroTik Error: " . $e->getMessage();
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotspot Login & Status</title>
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet" />
  <style>
    * { box-sizing: border-box; }
    body, html {
      margin: 0; padding: 0; height: 100%;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: #fff;
    }
    .container {
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 20px;
    }
    .box {
      background: rgba(255,255,255,0.08);
      padding: 30px 40px;
      border-radius: 15px;
      max-width: 460px;
      width: 100%;
      backdrop-filter: blur(8px);
      text-align: center;
    }
    h1 {
      text-align: center;
      margin-bottom: 25px;
      text-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    .input-group {
      margin-bottom: 18px;
      position: relative;
      text-align: left;
    }
    .input-group i {
      position: absolute;
      left: 15px;
      top: 50%;
      transform: translateY(-50%);
      color: rgba(255,255,255,0.7);
    }
    input[type="text"],
    input[type="password"] {
      width: 100%;
      padding: 12px 15px 12px 42px;
      border-radius: 8px;
      border: none;
      background: rgba(255,255,255,0.3);
      color: #fff;
    }
    input:focus {
      background: rgba(255,255,255,0.6);
      color: #000;
      outline: none;
    }
    .btn {
      padding: 12px 15px;
      border-radius: 8px;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.3s ease;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      user-select: none;
      border: none;
      margin-top: 10px;
      text-decoration: none;
      color: #fff;
    }
    .btn-login {
      background: #5a67d8;
      flex: 1 1 auto;
    }
    .btn-login:hover {
      background: transparent;
      color: #5a67d8;
      border: 2px solid #5a67d8;
      text-color: white;
    }
    .btn-buy {
      background: #f56565;
      flex: 1 1 auto;
    }
    .btn-buy:hover {
      background: transparent;
      color: #f56565;
      border: 2px solid #f56565;
    }
    .btn-logout {
      background: #e53e3e;
      margin-top: 15px;
      width: 100%;
      border: none;
      padding: 12px 15px;
      border-radius: 8px;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.3s ease;
    }
    .btn-logout:hover {
      background: transparent;
      color: #e53e3e;
      border: 2px solid #e53e3e;
    }
    .button-group {
      display: flex;
      gap: 15px;
      flex-wrap: wrap;
      justify-content: center;
      margin-top: 15px;
    }
    .status-box p {
      margin: 8px 0;
      font-size: 1rem;
      text-align: left;
    }
    .error {
      background: rgba(245, 101, 101, 0.8);
      padding: 10px;
      border-radius: 8px;
      margin-bottom: 15px;
      text-align: center;
    }
    @media (max-width: 480px) {
      .button-group {
        flex-direction: column;
      }
      .btn-login,
      .btn-buy {
        width: 100%;
      }
    }
  </style>
</head>
<body>
<div class="container">
  <div class="box">
    <h1><i class="fa-solid fa-wifi"></i> Hotspot</h1>

    <?php if ($error): ?>
      <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <?php if ($userInfo): ?>
      <div class="status-box">
        <p><strong>ðŸ‘¤ Username:</strong> <?= htmlspecialchars($userInfo['username']) ?></p>
        <p><strong>ðŸ“¦ Package:</strong> <?= htmlspecialchars($userInfo['profile']) ?></p>
        <p><strong>ðŸ“¶ IP:</strong> <?= htmlspecialchars($userInfo['ip']) ?></p>
        <p><strong>ðŸ”— MAC:</strong> <?= htmlspecialchars($userInfo['mac']) ?></p>
        <p><strong>â±ï¸ Uptime:</strong> <?= htmlspecialchars($userInfo['uptime']) ?></p>
        <p><strong>â¬†ï¸ Upload:</strong> <?= htmlspecialchars($userInfo['upload']) ?></p>
        <p><strong>â¬‡ï¸ Download:</strong> <?= htmlspecialchars($userInfo['download']) ?></p>
        <p><strong>â³ Remaining:</strong> <?= htmlspecialchars($userInfo['remaining_time']) ?></p>
      </div>
      <div class="button-group">
        <a class="btn btn-buy" href="payment.php" aria-label="Buy more time"><i class="fa-solid fa-cart-shopping"></i> Buy More Time</a>
        <a class="btn btn-logout" href="?logout=1" aria-label="Logout"><i class="fa-solid fa-right-from-bracket"></i> Logout</a>
      </div>
    <?php else: ?>
      <form method="POST" action="index.php" autocomplete="off" novalidate>
        <div class="input-group">
          <i class="fa-solid fa-user"></i>
          <input type="text" name="username" placeholder="Username" required />
        </div>
        <div class="input-group">
          <i class="fa-solid fa-lock"></i>
          <input type="password" name="password" placeholder="Password" required />
        </div>
        <div class="button-group">
          <button class="btn btn-login" type="submit">Login</button>
          <a class="btn btn-buy" href="payment.php"><i class="fa-solid fa-cart-shopping"></i> Buy Package</a>
        </div>
      </form>
    <?php endif; ?>
  </div>
</div>
</body>
</html>
