#include "battery.h"

#include <math.h>

#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "sdkconfig.h"
#include "settings.h"

static const char *TAG = "batt";

static adc_oneshot_unit_handle_t s_adc = NULL;
static adc_cali_handle_t s_cali = NULL;
static adc_channel_t s_chan;
static adc_unit_t s_unit;
static esp_timer_handle_t s_timer;

static float s_div = 11.0f, s_vmin = 10.0f, s_vmax = 12.6f;
static volatile float s_volts = 0;
static volatile int s_pin_mv = 0;
static volatile bool s_present = false;
static bool s_first = true;

// Below this at the pin, nothing is connected (or the pack is flat beyond any
// chemistry's floor through any sane divider).
static const int PRESENT_MV = 150;

void battery_reload_settings(void) {
    s_div = settings_get_f32("batt_div", 11.0f);
    s_vmin = settings_get_f32("batt_vmin", 10.0f);
    s_vmax = settings_get_f32("batt_vmax", 12.6f);
    if (s_div < 1.0f) s_div = 1.0f;
    if (s_vmax <= s_vmin) s_vmax = s_vmin + 0.1f;
}

static void sample(void *arg) {
    (void)arg;
    if (!s_adc) return;
    int sum = 0, n = 0;
    for (int i = 0; i < 16; i++) {
        int raw, mv;
        if (adc_oneshot_read(s_adc, s_chan, &raw) != ESP_OK) continue;
        if (s_cali && adc_cali_raw_to_voltage(s_cali, raw, &mv) == ESP_OK) sum += mv;
        else sum += raw * 3300 / 4095;   // uncalibrated fallback, 12-bit at 12 dB
        n++;
    }
    if (!n) return;
    int mv = sum / n;
    s_pin_mv = mv;
    s_present = mv > PRESENT_MV;
    float v = mv * 0.001f * s_div;
    // One-pole at ~5 s so a motor surge does not swing the percentage.
    s_volts = s_first ? v : s_volts + 0.2f * (v - s_volts);
    s_first = false;
}

esp_err_t battery_init(void) {
    battery_reload_settings();

    esp_err_t err = adc_oneshot_io_to_channel(CONFIG_UBOT_PIN_BATT_ADC, &s_unit, &s_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GPIO%d is not an ADC pin", CONFIG_UBOT_PIN_BATT_ADC);
        return err;
    }
    adc_oneshot_unit_init_cfg_t ucfg = { .unit_id = s_unit };
    err = adc_oneshot_new_unit(&ucfg, &s_adc);
    if (err != ESP_OK) return err;
    adc_oneshot_chan_cfg_t ccfg = { .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT };
    err = adc_oneshot_config_channel(s_adc, s_chan, &ccfg);
    if (err != ESP_OK) return err;
    // Weak internal pull-down (~45k) so a pin with nothing on it reads zero
    // and says "no sense", instead of floating at whatever it picks up. It
    // sits in parallel with the divider's lower leg, which is one more reason
    // batt_div is calibrated against a meter rather than computed.
    gpio_set_pull_mode((gpio_num_t)CONFIG_UBOT_PIN_BATT_ADC, GPIO_PULLDOWN_ONLY);

    adc_cali_curve_fitting_config_t cal = {
        .unit_id = s_unit, .chan = s_chan, .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_curve_fitting(&cal, &s_cali) != ESP_OK) {
        ESP_LOGW(TAG, "no ADC calibration data; readings are nominal");
        s_cali = NULL;
    }

    sample(NULL);
    const esp_timer_create_args_t targs = { .callback = sample, .name = "batt" };
    err = esp_timer_create(&targs, &s_timer);
    if (err == ESP_OK) err = esp_timer_start_periodic(s_timer, 1000000);
    ESP_LOGI(TAG, "sense on GPIO%d (ADC%d ch%d), divider %.2f, %.1f..%.1f V -> 0..100%%: %s",
             CONFIG_UBOT_PIN_BATT_ADC, (int)s_unit + 1, (int)s_chan, s_div, s_vmin, s_vmax,
             s_present ? "reading" : "nothing connected");
    return err;
}

float battery_voltage(void) { return s_present ? s_volts : 0.0f; }
int battery_pin_mv(void) { return s_pin_mv; }
bool battery_present(void) { return s_present; }

int battery_percent(void) {
    if (!s_present) return -1;
    float f = (s_volts - s_vmin) / (s_vmax - s_vmin);
    if (f < 0) f = 0;
    if (f > 1) f = 1;
    return (int)lroundf(f * 100.0f);
}
