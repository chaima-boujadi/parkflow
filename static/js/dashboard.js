document.addEventListener("DOMContentLoaded", () => {
    // 1. FLOW CHART (Line Chart)
    const flowCtx = document.getElementById('flowChart').getContext('2d');
    
    // Hourly flow mock matching today's database counts
    const hours = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00'];
    const entriesData = [2, 4, Math.max(2, entriesToday), Math.max(1, entriesToday - 1), Math.max(3, entriesToday + 1), entriesToday, Math.max(0, entriesToday - 2)];
    const exitsData = [1, 2, Math.max(1, exitsToday), Math.max(2, exitsToday + 1), Math.max(0, exitsToday - 1), exitsToday, Math.max(0, exitsToday - 3)];

    new Chart(flowCtx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: 'Entrées (Entries)',
                    data: entriesData,
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.05)',
                    tension: 0.35,
                    fill: true,
                    borderWidth: 2.5
                },
                {
                    label: 'Sorties (Exits)',
                    data: exitsData,
                    borderColor: '#f97316',
                    backgroundColor: 'rgba(249, 115, 22, 0.05)',
                    tension: 0.35,
                    fill: true,
                    borderWidth: 2.5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        font: {
                            family: "'Inter', 'Cairo', sans-serif",
                            size: 11
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#f1f5f9'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });

    // 2. ZONE CHART (Doughnut Chart)
    const zoneCtx = document.getElementById('zoneChart').getContext('2d');
    
    let chartLabels = [];
    let chartData = [];
    let chartColors = [];

    if (zoneNames && zoneNames.length > 0) {
        zoneNames.forEach((name, i) => {
            const occupied = zoneOccupied[i] || 0;
            const total = zoneTotals[i] || 0;
            const free = Math.max(0, total - occupied);
            
            // Push occupied slice
            chartLabels.push(`${name} - Occupé (${occupied})`);
            chartData.push(occupied);
            chartColors.push('#ef4444');
            
            // Push free slice
            chartLabels.push(`${name} - Libre (${free})`);
            chartData.push(free);
            chartColors.push('#10b981');
        });
    } else {
        // Fallback context
        chartLabels = [`Occupé (${occupiedSpots})`, `Disponible (${availableSpots})`];
        chartData = [occupiedSpots, availableSpots];
        chartColors = ['#ef4444', '#10b981'];
    }

    new Chart(zoneCtx, {
        type: 'doughnut',
        data: {
            labels: chartLabels,
            datasets: [{
                data: chartData,
                backgroundColor: chartColors,
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        padding: 10,
                        font: {
                            family: "'Inter', 'Cairo', sans-serif",
                            size: 11
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
});
