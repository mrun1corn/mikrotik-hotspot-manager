<?php
require_once __DIR__ . '/vendor/autoload.php';

use RouterOS\Client;
use RouterOS\Query;

session_start();

$mikrotikConfig = [
    'host' => '',
    'user' => '',
    'pass' => '',
    'port' => ,
];

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    if (!empty($_SESSION['username'])) {
        try {
            $client = new Client($mikrotikConfig);
            $query = (new Query('/ip/hotspot/active/print'))->where('user', $_SESSION['username']);
            $active = $client->query($query)->read();

            if (count($active)) {
                $remove = new Query('/ip/hotspot/active/remove');
                $remove->equal('.id', $active[0]['.id']);
                $client->query($remove);
            }
        } catch (Exception $e) {
            // Optional: Log error if needed
        }
    }
    session_destroy();
    header("Location: index.php?logged_out=1");
    exit;
}

