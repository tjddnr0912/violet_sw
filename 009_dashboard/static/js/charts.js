/**
 * Trading Dashboard - Chart Utilities
 */

// Chart.js 기본 설정
Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#495057';

/**
 * 숫자 포맷팅 (천 단위 구분)
 */
function formatNumber(num) {
    return new Intl.NumberFormat('ko-KR').format(num);
}

/**
 * 퍼센트 포맷팅
 */
function formatPercent(num) {
    const sign = num >= 0 ? '+' : '';
    return sign + num.toFixed(2) + '%';
}

/**
 * 날짜 포맷팅
 */
function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * API에서 데이터 가져오기
 */
async function fetchData(endpoint) {
    try {
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        console.error('Error fetching data:', error);
        return null;
    }
}

/**
 * 수익 분포 도넛 차트 생성
 */
function createProfitDistChart(canvasId, trades) {
    const wins = trades.filter(t => t.profit_pct > 0).length;
    const losses = trades.filter(t => t.profit_pct <= 0).length;

    return new Chart(document.getElementById(canvasId), {
        type: 'doughnut',
        data: {
            labels: ['Wins', 'Losses'],
            datasets: [{
                data: [wins, losses],
                backgroundColor: ['#198754', '#dc3545'],
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 20
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = ((context.raw / total) * 100).toFixed(1);
                            return `${context.label}: ${context.raw} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * 수익률 바 차트 생성
 */
function createPerformanceChart(canvasId, trades, limit = 10) {
    const recentTrades = trades.slice(0, limit).reverse();
    const labels = recentTrades.map(t => t.coin);
    const data = recentTrades.map(t => t.profit_pct);

    return new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Profit %',
                data: data,
                backgroundColor: data.map(v => v >= 0 ? '#198754' : '#dc3545'),
                borderRadius: 4,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return formatPercent(context.raw);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#e9ecef'
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
}

/**
 * 레짐별 수익 차트 생성
 */
function createRegimeChart(canvasId, trades) {
    const regimes = [...new Set(trades.map(t => t.regime))];
    const regimeData = regimes.map(r => {
        const regimeTrades = trades.filter(t => t.regime === r);
        const avg = regimeTrades.reduce((sum, t) => sum + t.profit_pct, 0) / regimeTrades.length;
        return avg;
    });

    const regimeColors = {
        'bullish': '#198754',
        'strong_bullish': '#0d6939',
        'bearish': '#dc3545',
        'strong_bearish': '#a71d2a',
        'neutral': '#6c757d',
        'ranging': '#0dcaf0'
    };

    return new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: {
            labels: regimes,
            datasets: [{
                label: 'Avg Profit %',
                data: regimeData,
                backgroundColor: regimes.map(r => regimeColors[r] || '#6c757d'),
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: {
                        color: '#e9ecef'
                    }
                },
                y: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

/**
 * 자동 새로고침 설정
 */
function setupAutoRefresh(intervalMs = 60000) {
    setInterval(() => {
        location.reload();
    }, intervalMs);
}

// 공통 유틸리티 내보내기
window.DashboardUtils = {
    formatNumber,
    formatPercent,
    formatDate,
    fetchData,
    createProfitDistChart,
    createPerformanceChart,
    createRegimeChart,
    setupAutoRefresh
};
