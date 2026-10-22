#include <assert.h>
#include <stdio.h>
#include "management_fragment.h"
int main(void) {
    management_fragment_t a={0},b={0};
    const uint8_t start[]={1,1,0,0,0,'{','"','a','"'};
    const uint8_t end[]={2,1,0,4,0,':','1','}'};
    assert(management_fragment_feed(&a,end,sizeof end,0)==-1);
    assert(management_fragment_feed(&a,start,sizeof start,1)==0);
    assert(management_fragment_feed(&b,start,sizeof start,1)==0);
    assert(management_fragment_feed(&a,end,sizeof end,2)==1);
    assert(!strcmp(a.data,"{\"a\":1}"));
    assert(management_fragment_feed(&a,end,sizeof end,3)==-1);
    assert(management_fragment_feed(&b,end,sizeof end,6000)==-1);
    assert(management_fragment_feed(&a,start,sizeof start,7000)==0);
    assert(management_fragment_feed(&a,end,sizeof end,7001)==1);
    uint8_t large[773];memset(large,'x',sizeof large);memcpy(large,(uint8_t[]){3,2,0,0,0},5);
    assert(management_fragment_feed(&a,large,sizeof large,8000)==-1);
    large[5]=0;assert(management_fragment_feed(&a,large,6,8000)==-1);
    // Every ATT MTU, including 23, can deliver a maximum-size request.
    for(int mtu=23;mtu<=517;mtu++) {
        memset(&a,0,sizeof a);
        for(int off=0;off<767;) {
            int n=mtu-8;if(n>767-off)n=767-off;
            uint8_t part[517];memset(part,'x',sizeof part);
            part[0]=(off?0:1)|(off+n==767?2:0);part[1]=3;part[2]=0;part[3]=off;part[4]=off>>8;
            int result=management_fragment_feed(&a,part,n+5,off);
            assert(result==(off+n==767?1:0));off+=n;
        }
        assert(strlen(a.data)==767);
    }
    puts("PASS: production BLE reassembly: all MTUs 23..517, independent peers, stale/duplicate/out-of-order/oversize/NUL rejection");
}
