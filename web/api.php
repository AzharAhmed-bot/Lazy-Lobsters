<?php
// Standalone JSON API endpoint.  GET /api.php?api=<action>
header('Content-Type: application/json');

$action = $_GET['api'] ?? '';

switch ($action) {
    case 'health':
        echo json_encode([
            'status' => 'ok',
            'time'   => date('c'),
            'server' => 'Lazy-Lobsters webcam viewer',
        ]);
        break;

    default:
        http_response_code(400);
        echo json_encode([
            'status' => 'error',
            'message' => 'unknown api action',
            'allowed' => ['health'],
        ]);
}
