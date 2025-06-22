<?php
// Set UTF-8 headers
header('Content-Type: text/html; charset=UTF-8');

// Set time zone
date_default_timezone_set('Asia/Dhaka');

// Detect user's IP address (for reference, not enforced)
$user_ip = $_SERVER['REMOTE_ADDR'];
error_log("Detected IP in payment.php: $user_ip");
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>bKash Payment Login</title>
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
    form {
      background: rgba(255, 255, 255, 0.08);
      padding: 30px 40px;
      border-radius: 15px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.15);
      width: 100%;
      max-width: 460px;
      backdrop-filter: blur(8px);
    }
    h1 {
      margin-bottom: 20px;
      font-weight: 700;
      text-align: center;
      text-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    label { display: block; margin-bottom: 8px; font-weight: 600; }
    .input-group {
      position: relative;
      margin-bottom: 20px;
    }
    .input-group i {
      position: absolute;
      left: 15px;
      top: 50%;
      transform: translateY(-50%);
      color: rgba(255,255,255,0.7);
      font-size: 1.1rem;
    }
    input[type="text"], input[type="file"] {
      width: 100%;
      padding: 12px 15px 12px 42px;
      border-radius: 8px;
      border: none;
      font-size: 1rem;
      background: rgba(255,255,255,0.3);
      color: #fff;
    }
    input[type="text"]:focus, input[type="file"]:focus {
      background: rgba(255,255,255,0.6);
      outline: none;
      color: #333;
    }
    .packages {
      display: flex;
      gap: 15px;
      flex-wrap: wrap;
      justify-content: center;
      margin-bottom: 25px;
    }
    .package {
      flex: 1 1 120px;
      background: rgba(255,255,255,0.1);
      padding: 15px;
      text-align: center;
      border-radius: 10px;
      cursor: pointer;
      border: 2px solid transparent;
      transition: all 0.3s ease;
    }
    .package:hover,
    .package.selected {
      background: rgba(255,255,255,0.2);
      border-color: #fff;
    }
    .package input {
      display: none;
    }
    input[type="submit"] {
      width: 100%;
      padding: 12px 15px;
      border-radius: 8px;
      border: 2px solid transparent;
      background: #5a67d8;
      color: white;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.3s ease;
    }
    input[type="submit"]:hover {
      background: transparent;
      color: #5a67d8;
      border-color: #5a67d8;
    }
    @media (max-width: 480px) {
      form { padding: 20px; }
    }
  </style>
</head>
<body>
  <div class="container">
    <form action="submit_trx.php" method="post" enctype="multipart/form-data">
      <h1><i class="fa-solid fa-wifi"></i> Login & Payment</h1>

      <!-- Package Selection -->
      <label>Select a Package:</label>
      <div class="packages">
        <label class="package">
          <input type="radio" name="package" value="1_day" required />
          <strong>1 Day</strong><br>
          ৳10
        </label>
        <label class="package">
          <input type="radio" name="package" value="7_days" />
          <strong>7 Days</strong><br>
          ৳30
        </label>
        <label class="package">
          <input type="radio" name="package" value="30_days" />
          <strong>30 Days</strong><br>
          ৳100
        </label>
      </div>

      <!-- bKash Number -->
      <label for="bkash_number">bKash Number</label>
      <div class="input-group">
        <i class="fa-solid fa-phone"></i>
        <input type="text" id="bkash_number" name="bkash_number" placeholder="Enter your bKash number" required pattern="\d{11}" title="Enter 11-digit bKash number" />
      </div>

      <!-- Proof of Payment -->
      <label for="proof_image">Proof of Payment (Image)</label>
      <div class="input-group">
        <i class="fa-solid fa-image"></i>
        <input type="file" id="proof_image" name="proof_image" accept="image/*" required />
      </div>

      <!-- IP (hidden) -->
      <input type="hidden" name="ip" value="<?= htmlspecialchars($user_ip) ?>" />

      <input type="submit" value="Submit Payment" />
    </form>
  </div>

  <script>
    // Highlight selected package visually
    const packages = document.querySelectorAll('.package input');
    packages.forEach(pkg => {
      pkg.addEventListener('change', () => {
        document.querySelectorAll('.package').forEach(p => p.classList.remove('selected'));
        pkg.closest('.package').classList.add('selected');
      });
    });
  </script>
</body>
</html>
