<?php
require_once __DIR__ . '/vendor/autoload.php';
$config = json_decode(file_get_contents(__DIR__ . '/config.json'), true);

use RouterOS\Client;
use RouterOS\Query;

session_start();

$mikrotikConfig = $config['mikrotik'];
$mikrotikConfig['host'];
$mikrotikConfig['user'];
$mikrotikConfig['pass'];
$mikrotikConfig['port'];    


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
        }
    }
    session_destroy();
    header("Location: index.php?logged_out=1");
    exit;
}

