#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "management.h"
#include "drive.h"
#include "ulog.h"
#include "cJSON.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

struct queue {pthread_mutex_t mu;unsigned cap,size,count,read,write;char*data;};
QueueHandle_t xQueueCreate(unsigned n,unsigned size){struct queue*q=calloc(1,sizeof*q);pthread_mutex_init(&q->mu,NULL);q->cap=n;q->size=size;q->data=calloc(n,size);return q;}
int xQueueSend(QueueHandle_t q,const void*p,unsigned wait){pthread_mutex_lock(&q->mu);int ok=q->count<q->cap;if(ok){memcpy(q->data+q->write*q->size,p,q->size);q->write=(q->write+1)%q->cap;q->count++;}pthread_mutex_unlock(&q->mu);return ok;}
int xQueueReceive(QueueHandle_t q,void*p,unsigned wait){for(unsigned i=0;;i++){pthread_mutex_lock(&q->mu);int ok=q->count>0;if(ok){memcpy(p,q->data+q->read*q->size,q->size);q->read=(q->read+1)%q->cap;q->count--;}pthread_mutex_unlock(&q->mu);if(ok||i>=wait)return ok;usleep(1000);}}
unsigned uxQueueSpacesAvailable(QueueHandle_t q){pthread_mutex_lock(&q->mu);unsigned n=q->cap-q->count;pthread_mutex_unlock(&q->mu);return n;}
void vQueueDelete(QueueHandle_t q){pthread_mutex_destroy(&q->mu);free(q->data);free(q);}
void xQueueReset(QueueHandle_t q){pthread_mutex_lock(&q->mu);q->count=q->read=q->write=0;pthread_mutex_unlock(&q->mu);}
SemaphoreHandle_t xSemaphoreCreateMutex(void){pthread_mutex_t*m=malloc(sizeof*m);pthread_mutex_init(m,NULL);return m;}
int xSemaphoreTake(SemaphoreHandle_t m,unsigned wait){pthread_mutex_lock(m);return 1;}
void xSemaphoreGive(SemaphoreHandle_t m){pthread_mutex_unlock(m);}
typedef struct {void(*fn)(void*);void*arg;} task_t;
static void*task(void*arg){task_t*t=arg;t->fn(t->arg);return NULL;}
int xTaskCreate(void(*fn)(void*),const char*n,unsigned stack,void*arg,unsigned pri,TaskHandle_t*out){pthread_t thread;task_t*t=malloc(sizeof*t);*t=(task_t){fn,arg};if(out)*out=t;int rc=pthread_create(&thread,NULL,task,t);pthread_detach(thread);return !rc;}
void vTaskDelay(unsigned ms){usleep(ms*1000);}
int64_t esp_timer_get_time(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (int64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
uint32_t esp_random(void){return 1234;}
int esp_app_get_elf_sha256(char*out,unsigned n){snprintf(out,n,"image");return 6;}
const char*sysinfo_fw_version(void){return "test";}
void sysinfo_image_id(char out[65]){strcpy(out,"image");}
const char*sysinfo_project(void){return "ubot_base";}
const char*sysinfo_reset_reason(void){return "host";}
void ulog_set_boot(const char*s){}
const char*ulog_previous_boot(void){return "previous";}
const char*ulog_previous_panic(void){return "";}
bool ulog_read(uint32_t*c,char*out,size_t n,uint32_t*lost){return false;}
bool ulog_previous_read(uint32_t*c,char*out,size_t n,uint32_t*lost){return false;}
void net_ota_outcome(char*out,size_t n){snprintf(out,n,"none");}
esp_err_t net_ota_confirm(void){return ESP_OK;}
bool net_wifi_trial_busy(void){return false;}
int net_wifi_trial_result(void){return 0;}
void net_wifi_trial_cancel(void){}
void net_ota_cancel(void){}
bool net_ota_busy(void){return false;}
const char*net_ota_status(void){return "idle";}
static atomic_bool gate,moving,blocked,entered;
static atomic_int calls,stops;
esp_err_t drive_maintenance_claim(bool ota){bool expected=false;return atomic_compare_exchange_strong(&gate,&expected,true)?ESP_OK:ESP_ERR_INVALID_STATE;}
bool drive_maintenance_release(bool ota){gate=false;return true;}
void drive_maintenance_cancel(void){}
void drive_calibrate_abort(void){}
void drive_stop(void){moving=false;stops++;}
void drive_estop(void){drive_stop();}
bool drive_calibrate_busy(void){return false;}
bool drive_calibrate_last(drive_cal_result_t*r){r->ok=true;return true;}
void drive_get_status(drive_status_t*s){memset(s,0,sizeof*s);s->enabled=true;s->cmd_active=moving;}
int drive_csv_line(char*out,size_t n){return snprintf(out,n,"1,2,3");}
const char *const *drive_param_names(size_t*n){static const char*names[]={"kp","vmax"};*n=2;return names;}
static int handler(command_context_t*ctx,int argc,char**argv){
    calls++;
    if(!strcmp(argv[0],"block")){entered=true;while(blocked)usleep(1000);}
    if(!strcmp(argv[0],"drive")||!strcmp(argv[0],"wheel")){moving=true;return 0;}
    if(!strcmp(argv[0],"large")){for(int i=0;i<30;i++)command_printf(ctx,"line %02d abcdefghijklmnopqrstuvwxyz abcdefghijklmnopqrstuvwxyz abcdefghijklmnopqrstuvwxyz\n",i);}
    else command_printf(ctx,"ok\n");
    return 0;
}
static void send(mgmt_client_t c,int id,const char*body){char buf[768];snprintf(buf,sizeof buf,"{\"id\":%d,\"session\":%u,%s}",id,c,body);assert(management_receive(c,buf)==ESP_OK);}
static cJSON*wait_event(mgmt_client_t c,const char*type,int id){char buf[MGMT_FRAME];int64_t end=esp_timer_get_time()+4000000;while(esp_timer_get_time()<end){if(management_pop(c,buf)){cJSON*r=cJSON_Parse(buf);assert(r);const char*t=cJSON_GetStringValue(cJSON_GetObjectItem(r,"type"));int rid=cJSON_GetObjectItem(r,"id")->valueint;if(t&&!strcmp(t,type)&&(id<0||rid==id))return r;cJSON_Delete(r);}usleep(1000);}fprintf(stderr,"missing %s id %d\n",type,id);abort();}
static int code(mgmt_client_t c,int id){cJSON*r=wait_event(c,"finished",id);int n=cJSON_GetObjectItem(r,"code")->valueint;cJSON_Delete(r);return n;}
static int accepted(mgmt_client_t c,int id){cJSON*r=wait_event(c,"accepted",id);int n=cJSON_GetObjectItem(r,"job")->valueint;cJSON_Delete(r);return n;}
int main(void){
    assert(management_init(handler)==ESP_OK);
    mgmt_client_t a=management_open(),b=management_open();assert(a&&b);
    cJSON_Delete(wait_event(a,"hello",0));cJSON_Delete(wait_event(b,"hello",0));
    assert(management_receive(a,"{")==ESP_OK);assert(code(a,0)==2);
    send(a,1,"\"op\":\"exec\",\"args\":[\"status\"]");accepted(a,1);assert(code(a,1)==0);
    int previous=calls;send(a,1,"\"op\":\"exec\",\"args\":[\"status\"]");assert(code(a,1)==2);assert(calls==previous);
    send(a,2,"\"op\":\"exec\",\"args\":[\"drive\",\"0.1\",\"0\",\"0.4\"]");int jid=accepted(a,2);usleep(70000);assert(moving);
    send(b,1,"\"op\":\"exec\",\"args\":[\"drive\",\"0.1\",\"0\",\"1\"]");accepted(b,1);assert(code(b,1)==1);
    send(b,2,"\"op\":\"exec\",\"args\":[\"wheel\",\"A\",\"zero\"]");accepted(b,2);assert(code(b,2)==1);
    management_close(a);assert(moving);usleep(500000);assert(!moving);
    a=management_open();cJSON_Delete(wait_event(a,"hello",0));char body[256];snprintf(body,sizeof body,"\"op\":\"result\",\"job\":%d",jid);send(a,1,body);cJSON*r=wait_event(a,"result",1);assert(cJSON_IsTrue(cJSON_GetObjectItem(r,"done")));assert(cJSON_GetObjectItem(r,"code")->valueint==0);cJSON_Delete(r);
    send(a,2,"\"op\":\"exec\",\"args\":[\"drive\",\"0.1\",\"0\",\"0\"]");jid=accepted(a,2);usleep(70000);assert(moving);
    snprintf(body,sizeof body,"\"op\":\"renew\",\"job\":%d,\"seq\":1",jid);send(a,3,body);assert(code(a,3)==0);send(a,4,body);assert(code(a,4)==1);
    assert(code(a,2)==124);assert(!moving);send(a,5,body);assert(code(a,5)==1);
    send(a,6,"\"op\":\"exec\",\"args\":[\"wheel\",\"A\",\"goto\",\"3\"],\"deadline_ms\":150");accepted(a,6);assert(code(a,6)==124);
    // A slow subscriber does not delay another client's stop or large command completion.
    management_stream(b,50);send(a,7,"\"op\":\"exec\",\"args\":[\"large\"]");accepted(a,7);assert(code(a,7)==0);
    blocked=true;send(a,8,"\"op\":\"exec\",\"args\":[\"block\"]");accepted(a,8);while(!entered)usleep(1000);
    int before=stops;send(a,9,"\"op\":\"exec\",\"args\":[\"estop\"]");assert(code(a,9)==0);assert(stops>before);
    blocked=false;usleep(100000);
    puts("PASS: real command service: malformed/replay refusal, motion ownership, disconnected completion, lease expiry/replay, position deadline, slow subscriber isolation, urgent stop bypass");
    return 0;
}
