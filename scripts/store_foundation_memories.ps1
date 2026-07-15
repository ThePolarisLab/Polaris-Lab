$ErrorActionPreference = "Stop"
$baseUrl = "http://127.0.0.1:8001/api/v1/memories"

$memories = @(
    @{
        title = "Every Builder matters"
        content = "Recognition is not the measure of a Builder. Contribution is. Polaris recognizes the dignity and value of every Builder, regardless of scale, wealth, visibility, title, or public recognition."
        memory_type = "lesson"
        source = "founder"
        importance = 5
        occurred_at = "2026-07-14T20:00:00"
    },
    @{
        title = "Foundation dedication"
        content = "Dedicated to every Builder whose wisdom deserved to outlive them."
        memory_type = "lesson"
        source = "founder"
        importance = 5
        occurred_at = "2026-07-14T20:01:00"
    }
)

foreach ($memory in $memories) {
    $json = $memory | ConvertTo-Json
    $response = Invoke-RestMethod -Method Post -Uri $baseUrl -ContentType "application/json" -Body $json
    Write-Host "Stored memory ID $($response.id): $($response.title)"
}
