document.addEventListener('DOMContentLoaded', function () {
    const table = document.getElementById('achievements-table');
    const chartLinks = table.querySelectorAll('.column-chart');
    let chartInstance = null;

    chartLinks.forEach(link => {
        link.addEventListener('click', function (event) {
            event.preventDefault();
            const column = this.getAttribute('data-column');
            generateColumnChart(column);
        });
    });

    function generateColumnChart(column) {
        const data = [];
        const rows = document.querySelectorAll('#achievements-table tbody tr');

        rows.forEach(row => {
            const player = row.cells[0].textContent.trim();
            const valueCell = row.cells[columnIndex(column)];
            if (valueCell) {
                let value;
                if (column === 'fastest_frame_won' || column === 'longest_frame_won') {
                    const timeParts = valueCell.textContent.trim().split(':');
                    value = parseInt(timeParts[0]) * 3600 + parseInt(timeParts[1]) * 60 + parseFloat(timeParts[2]);
                } else {
                    value = parseFloat(valueCell.textContent.trim());
                }
                data.push({ label: player, value: value });
            }
        });

        const ctx = document.getElementById('myChart').getContext('2d');

        if (chartInstance) {
            chartInstance.destroy();
        }
        chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(item => item.label),
                datasets: [{
                    label: column.replace('_', ' ').toUpperCase(),
                    data: data.map(item => item.value),
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value, index, values) {
                                if (column === 'fastest_frame_won' || column === 'longest_frame_won') {
                                    const minutes = Math.floor(value / 60);
                                    const seconds = Math.floor(value % 60);
                                    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
                                }
                                return value;
                            }
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                let value = context.raw;
                                if (column === 'fastest_frame_won' || column === 'longest_frame_won') {
                                    const minutes = Math.floor(value / 60);
                                    const seconds = Math.floor(value % 60);
                                    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
                                }
                                return value;
                            }
                        }
                    }
                }
            }
        });
    }

    function columnIndex(columnName) {
        const headers = document.querySelectorAll('#achievements-table th a');
        for (let i = 0; i < headers.length; i++) {
            if (headers[i].getAttribute('data-column') === columnName) {
                return i + 1;
            }
        }
        return -1;
    }
});
