/* Runtime interaction model for the fingerprinted build; included after the
 * read-only helpers. No external process probe, memory writes, or screenshots.
 * Object types follow CGameObject; x64 base fields and row bounds were checked
 * against this executable's object lookup and rendering code.
 */
typedef struct { uint32_t id; uintptr_t object; int kind; int32_t x, y; double distance; int rank; } NearbyTarget;
static NearbyTarget nearby_targets[128];
static int nearby_count;
static unsigned nearby_tick;
static uintptr_t nearby_area;
static int nearby_mode=-1;
static uint32_t prepared_id=UINT32_MAX;
static int prepared_x,prepared_y;
static unsigned prepared_tick;
static unsigned char nearby_rows[32768*16];

static int point_to_screen(uintptr_t area, uintptr_t video, int32_t x, int32_t y, double *sx, double *sy) {
    int32_t view[2], scroll[2], dimensions[2], offsets[2];
    uint16_t rw=0,rh=0; float zoom=0;
    if (!read_memory(area+0x650,view,8) || !read_memory(area+0x698,scroll,8)
        || !read_memory(video+0x150,dimensions,8) || !read_memory(video+0x188,offsets,8)
        || !read_memory((uintptr_t)engine+0x72120c,&rw,2) || !read_memory((uintptr_t)engine+0x721210,&rh,2)
        || !read_memory(area+0xa14,&zoom,4) || !rw || !rh || !isfinite(zoom) || zoom<0.125 || zoom>8) return 0;
    *sx=(((double)(x-scroll[0]+view[0])*dimensions[0]/rw)-offsets[1])/zoom;
    *sy=(((double)(y-scroll[1]+view[1])*dimensions[1]/rh)-offsets[0])/zoom;
    return isfinite(*sx) && isfinite(*sy);
}

static uintptr_t object_for_id(uint32_t id) {
    uint16_t generation=0;
    uintptr_t row=(uintptr_t)engine+0x72d860+((id>>16)&0x7fff)*16;
    if (!read_memory(row,&generation,2) || generation!=(uint16_t)id) return 0;
    return read_pointer(row+8);
}

static int target_point(uintptr_t object, uintptr_t area, int *kind, int32_t *x, int32_t *y) {
    unsigned char base[32]; uintptr_t owner=0; int32_t point[2];
    if (!object || !read_memory(object,base,sizeof(base))) return 0;
    uint8_t type=base[8];
    memcpy(&owner,base+0x18,8); memcpy(point,base+0xc,8);
    if (owner!=area) return 0;
    if (type!=0x31 && type!=0x11 && type!=0x21 && type!=0x41) return 0;
    if (type==0x31) {
        uint8_t ea=255; int32_t alternate=0, visible1=0, visible2=0; uint32_t state=0;
        if (!read_memory(object+0x38,&ea,1)
            || !read_memory(object+0x4bbc,&alternate,4)
            || !read_memory(object+(alternate ? 0xfe8 : 0x1c98),&state,4)
            || (state & (0xfc0u|0x10u|0x400000u))
            || !read_memory(object+0x3908,&visible1,4) || !visible1
            || !read_memory(object+0x390c,&visible2,4) || !visible2) return 0;
    } else if (type==0x11) {
        /* Mirrors Infinity_ClickObjectInWorld's CONTAINER rectangle getter.
         * The compared build constant at RVA 0x62c89a is 0x11.
         */
        uintptr_t method=read_pointer(read_pointer(object)+0x180);
        IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64 *)(engine+((IMAGE_DOS_HEADER *)engine)->e_lfanew);
        if (method<(uintptr_t)engine+0x1000 || method>=(uintptr_t)engine+nt->OptionalHeader.SizeOfImage) return 0;
        int32_t bounds[4]={0};
        void *result=((void *(*)(void *, void *))method)((void *)object,bounds);
        if (result!=bounds || bounds[2]<=bounds[0] || bounds[3]<=bounds[1]) return 0;
        point[0]=bounds[0]+(bounds[2]-bounds[0])/2;
        point[1]=bounds[1]+(bounds[3]-bounds[1])/2;
        uint16_t container_type=0; int32_t item_count=0;
        if (!read_memory(object+0x590,&container_type,2) || !read_memory(object+0x570,&item_count,4)
            || (container_type==4 && item_count==0)) return 0;
    } else if (type==0x41) {
        /* ARE region type/flags copied by this build's 0x2162a0 constructor.
         * Proximity triggers are automatic scripts, not press-A objects.
         */
        uint16_t region_type=0; uint32_t flags=0; int32_t text=-1,bounds[4];
        if (!read_memory(object+0x538,&region_type,2) || !read_memory(object+0x578,&flags,4)
            || !read_memory(object+0x57c,&text,4) || !read_memory(object+0x53c,bounds,16)
            || region_type<1 || region_type>2 || (flags&0x100)
            || (region_type==1 && text==-1 && !(flags&0x400))) return 0;
        if (bounds[2]>bounds[0] && bounds[3]>bounds[1]) {
            point[0]=bounds[0]+(bounds[2]-bounds[0])/2;
            point[1]=bounds[1]+(bounds[3]-bounds[1])/2;
        }
        if (region_type==2) type=0x42; /* UI action: travel, same underlying CGameTrigger */
    }
    if (point[0]<1 || point[1]<1 || point[0]>32767 || point[1]>32767) return 0;
    *kind=type; *x=point[0]; *y=point[1]; return 1;
}

static int interaction_context(uintptr_t *game, uintptr_t *area, uintptr_t *video) {
    uintptr_t chitin=read_pointer((uintptr_t)engine+0x72c278);
    *game=read_pointer(chitin+0x10c8); *video=read_pointer(chitin+0x268);
    uint8_t index=255;
    if (!*game || !*video || !read_memory(*game+0xa178,&index,1) || index>11) return 0;
    *area=read_pointer(*game+0xa180+(uintptr_t)index*8);
    return *area!=0;
}

static void refresh_nearby_targets(uintptr_t game, uintptr_t area, int mode) {
    unsigned now=get_ticks();
    if (nearby_area==area && nearby_mode==mode && (unsigned)(now-nearby_tick)<100) return;
    nearby_area=area; nearby_mode=mode; nearby_tick=now; nearby_count=0;
    int16_t party_count=0; uint32_t party_ids[6]={0}; int32_t selected=0;
    if (!read_memory(game+0xa218,&party_count,2) || party_count<1 || party_count>6
        || !read_memory(game+0xa200,party_ids,(size_t)party_count*4)) return;
    uint32_t leader_id=party_ids[0];
    if (read_memory(game+0xa2b0,&selected,4) && selected>0 && selected<=6) {
        uintptr_t head=read_pointer(game+0xa2a0);
        if (!head || !read_memory(head+0x10,&leader_id,4)) return;
    }
    uintptr_t leader=object_for_id(leader_id);
    int32_t origin[2];
    if (!leader || read_pointer(leader+0x18)!=area || !read_memory(leader+0xc,origin,8)) return;
    uintptr_t sprite_vtable=read_pointer(leader);
    int16_t highest=-1;
    if (!read_memory((uintptr_t)engine+0x72d854,&highest,2) || highest<0) return;
    if (!read_memory((uintptr_t)engine+0x72d860,nearby_rows,((size_t)highest+1)*16)) return;
    for (int slot=0; slot<=highest && nearby_count<128; ++slot) {
        const unsigned char *row=nearby_rows+slot*16;
        uint16_t generation; uintptr_t object;
        memcpy(&generation,row,2); memcpy(&object,row+8,8);
        if (!object || generation>=0x8000) continue;
        uint32_t id=((uint32_t)slot<<16)|generation;
        int party=0; for (int n=0;n<party_count;++n) if (id==party_ids[n]) party=1;
        /* Explicit Talk includes companions, but never the speaking leader.
         * Automatic proximity still omits the party; Attack omits allies.
         */
        if (party && mode!=2 && mode!=3) continue;
        if (mode==3 && id==leader_id) continue;
        int kind=0; int32_t x=0,y=0;
        if (!target_point(object,area,&kind,&x,&y)) continue;
        if (kind==0x31 && read_pointer(object)!=sprite_vtable) continue;
        if (mode!=0 && kind!=0x31) continue;
        uint8_t ea=255;
        if (kind==0x31 && (!read_memory(object+0x38,&ea,1) || ((mode==0 || mode==3) && ea>=200))) continue;
        double dx=(double)x-origin[0],dy=((double)y-origin[1])*1.333333;
        if (kind==0x11 || kind==0x41 || kind==0x42) {
            int32_t bounds[4];
            if (read_memory(object+(kind==0x11 ? 0x538 : 0x53c),bounds,16)
                && bounds[2]>bounds[0] && bounds[3]>bounds[1]) {
                dx=origin[0]<bounds[0] ? (double)bounds[0]-origin[0] : origin[0]>bounds[2] ? (double)bounds[2]-origin[0] : 0;
                dy=(origin[1]<bounds[1] ? (double)bounds[1]-origin[1] : origin[1]>bounds[3] ? (double)bounds[3]-origin[1] : 0)*1.333333;
            }
        }
        double distance=sqrt(dx*dx+dy*dy);
        if (distance>(mode==0 ? 140 : 800)) continue;
        nearby_targets[nearby_count++]=(NearbyTarget){id,object,kind,x,y,distance,mode==1 && ea<200 ? 1 : 0};
    }
    /* Small, deterministic order: nearest target first. */
    for (int n=1;n<nearby_count;++n) {
        NearbyTarget value=nearby_targets[n]; int at=n;
        while (at>0 && (nearby_targets[at-1].rank>value.rank
            || (nearby_targets[at-1].rank==value.rank && nearby_targets[at-1].distance>value.distance))) {
            nearby_targets[at]=nearby_targets[at-1]; --at;
        }
        nearby_targets[at]=value;
    }
}

static int dispatch_nearby(lua_State *state, int operation, uint32_t argument, int mode, void *window, int width, int height, int focused) {
    double values[7]={0}; uintptr_t game=0,area=0,video=0;
    if (focused && window && interaction_context(&game,&area,&video)) {
        if (mode<0 || mode>3) mode=0;
        refresh_nearby_targets(game,area,mode);
        values[6]=nearby_count;
        NearbyTarget *target=NULL;
        if (operation==6 && argument>=1 && argument<=(uint32_t)nearby_count) target=&nearby_targets[argument-1];
        if (operation==7 || operation==8 || operation==15) for (int n=0;n<nearby_count;++n) if (nearby_targets[n].id==argument) target=&nearby_targets[n];
        int kind=0; int32_t x=0,y=0; double sx=0,sy=0;
        if (target && object_for_id(target->id)==target->object && target_point(target->object,area,&kind,&x,&y)
            && point_to_screen(area,video,x,y,&sx,&sy) && sx>=4 && sy>=4 && sx<width-4 && sy<height-height*85/768-4) {
            values[0]=1; values[1]=target->id; values[2]=sx; values[3]=sy;
            values[4]=kind; values[5]=target->distance;
            if (operation==15) {
                /* CGameArea's examined target-click helper at 0x19be70 calls
                 * object virtual +0x78 with a world CPoint pointer. Dispatch
                 * the captured object directly, without the mouse ID pair
                 * (area+0x240/0x244) required by the mouse-up handler.
                 */
                uintptr_t method=read_pointer(read_pointer(target->object)+0x78);
                IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64 *)(engine+((IMAGE_DOS_HEADER *)engine)->e_lfanew);
                if (method>=(uintptr_t)engine+0x1000 && method<(uintptr_t)engine+nt->OptionalHeader.SizeOfImage) {
                    int32_t point[2]={x,y};
                    ((void (*)(void *,const int32_t *))method)((void *)target->object,point);
                } else values[0]=0;
            }
            if (operation==7 || operation==8) {
                int iy=(int)sy-(kind==0x31 ? (int)(16.0*height/768) : 0);
                if (iy<1) iy=1;
                if (operation==7) {
                    prepared_id=target->id; prepared_x=(int)sx; prepared_y=iy; prepared_tick=get_ticks();
                    synchronize_pointer(window,prepared_x,prepared_y);
                } else if (prepared_id==target->id && (unsigned)(get_ticks()-prepared_tick)>=80
                    && (unsigned)(get_ticks()-prepared_tick)<1000) {
                    int mx=0,my=0; mouse_state(&mx,&my);
                    if (abs((int)sx-prepared_x)>8 || abs(iy-prepared_y)>8) {
                        prepared_x=(int)sx; prepared_y=iy; prepared_tick=get_ticks();
                        synchronize_pointer(window,prepared_x,prepared_y); values[0]=2;
                    } else if (abs(mx-prepared_x)<=3 && abs(my-prepared_y)<=3) {
                        mouse_click(window,prepared_x,prepared_y,1); prepared_id=UINT32_MAX;
                    } else {values[0]=0; prepared_id=UINT32_MAX;}
                } else values[0]=0;
            }
        }
    }
    if (operation!=6) log_runtime(operation,(int)argument,mode,(int)values[0]);
    for (int n=0;n<7;++n) push_number(state,values[n]);
    return 7;
}

/* Standard ground orders, extended through the stock shift-click path before
 * arrival. Full action clearing is reserved for start/ownership change/stop;
 * turns discard only pending orders, preserving the current movement action.
 * RUN continuation keeps one live MoveToPoint and updates only its guarded
 * destination; WALK uses the same path for turns and queued straight legs.
 * No mouse steering.
 */
static uintptr_t steering_area;
static uint32_t steering_leader=UINT32_MAX;
static int32_t steering_target[2];
static int steering_owned,steering_run;
static uint32_t steering_members[6];
static int steering_count;
static void (*group_clear_actions)(void *);
static void (*group_move)(void *,uint64_t,int,uint16_t,uint64_t);
static void (*prepare_group_run)(void *);
static void (*clear_pending_actions)(void *,int);
static uint16_t (*request_move_path)(void *,const int32_t *);
static int point_is_writable(uintptr_t address) {
    MEMORY_BASIC_INFORMATION info;
    if (!address || (address&7) || VirtualQuery((void *)address,&info,sizeof(info))!=sizeof(info)
        || info.State!=MEM_COMMIT || (info.Protect&(PAGE_GUARD|PAGE_NOACCESS))
        || (info.Protect!=PAGE_READWRITE && info.Protect!=PAGE_WRITECOPY)) return 0;
    return address>=(uintptr_t)info.BaseAddress
        && address+8<=(uintptr_t)info.BaseAddress+info.RegionSize;
}
static int pending_move(uintptr_t actor,int32_t *count,uintptr_t *action) {
    *action=0;
    if (!read_memory(actor+0x348,count,4) || *count<0 || *count>1) return 0;
    if (!*count) return 1;
    uintptr_t node=read_pointer(actor+0x338);
    *action=read_pointer(node+0x10); uint16_t opcode=0;
    return *action && read_memory(*action,&opcode,2) && opcode==23;
}
static int retarget_active_move(uintptr_t actor,uintptr_t area,int32_t *destination) {
    uint16_t opcode=0; int32_t queued=0; uintptr_t action=0;
    int16_t width=0,height=0;
    if (!request_move_path || read_pointer(actor)!=(uintptr_t)engine+0x649328
        || read_pointer(actor+0x18)!=area || !read_memory(actor+0x3f0,&opcode,2) || opcode!=23
        || !point_is_writable(actor+0x460) || !pending_move(actor,&queued,&action) || queued!=1
        || !read_memory(action+0x70,destination,8)
        || !read_memory(area+0x688,&width,2) || !read_memory(area+0x68c,&height,2)
        || destination[0]<1 || destination[1]<1 || destination[0]>width || destination[1]>height) return 0;
    /* Preserve the current MoveToPoint identity and all animation state. The
     * only direct write is its 8-byte destination (CAIAction point at +0x70,
     * verified in 124650). Stock path request 41d350 replans asynchronously
     * while the current route remains available. No SetCurrentAction call.
     */
    memcpy((void *)(actor+0x460),destination,8);
    clear_pending_actions((void *)actor,0);
    request_move_path((void *)actor,destination);
    return 1;
}
static int selected_origin(uintptr_t game,uintptr_t area,uint32_t *id,int32_t *point) {
    int32_t count=0;
    if (!read_memory(game+0xa2b0,&count,4) || count<1 || count>6) return 0;
    uintptr_t head=read_pointer(game+0xa2a0);
    if (!head || !read_memory(head+0x10,id,4)) return 0;
    uintptr_t actor=object_for_id(*id);
    return actor && read_pointer(actor+0x18)==area && read_memory(actor+0xc,point,8);
}
static int steering_selection(uintptr_t game,uint32_t *members) {
    int32_t count=0;
    if (!read_memory(game+0xa2b0,&count,4) || count<1 || count>6) return 0;
    uintptr_t node=read_pointer(game+0xa2a0);
    for (int index=0;index<count;++index) {
        if (!node || !read_memory(node+0x10,&members[index],4)) return 0;
        node=read_pointer(node);
    }
    return count;
}
static int dispatch_steering(lua_State *state,int operation,int dx,int dy,int focused,int extend) {
    uintptr_t game=0,area=0,video=0; uint32_t id=UINT32_MAX; int32_t origin[2]; double remaining=-1;
    int issued=0;
    if ((focused || operation==11) && interaction_context(&game,&area,&video) && selected_origin(game,area,&id,origin)) {
        if (operation==11) {
            if (dx && steering_owned && steering_area==area && steering_leader==id && group_clear_actions)
                group_clear_actions((void *)(game+0xa290));
            steering_owned=0; steering_leader=UINT32_MAX; log_runtime(operation,dx,0,0);
        }
        if (operation==9 && dx>=-10000 && dx<=10000 && dy>=-10000 && dy<=10000) {
            double length=sqrt((double)dx*dx+(double)dy*dy);
            uint16_t formation=0;
            int32_t count=0; read_memory(game+0xa2b0,&count,4);
            if (length>0 && group_clear_actions && group_move && prepare_group_run && read_memory(game+0xb56c,&formation,2) && formation<=12) {
                uint32_t members[6]; int member_count=steering_selection(game,members);
                if (!member_count) goto remaining_distance;
                int32_t run=0; read_memory(game+0xb9c0,&run,4);
                int same_owner=member_count && steering_owned && steering_area==area && steering_leader==id
                    && member_count==steering_count && !memcmp(members,steering_members,member_count*4);
                uintptr_t actors[6]; int active_move=same_owner && clear_pending_actions!=NULL;
                for (int index=0;active_move && index<member_count;++index) {
                    uint16_t action=0;
                    actors[index]=object_for_id(members[index]);
                    if (!actors[index] || read_pointer(actors[index]+0x18)!=area
                        || !read_memory(actors[index]+0x3f0,&action,2)
                        || (action!=23 && action!=0) || (index==0 && action!=23)) active_move=0;
                }
                int continuing=extend && same_owner && run==steering_run;
                /* WALK turns also need to retain the live action: replacing
                 * it restarts elapsed animation ticks even without an idle
                 * frame. Straight WALK extensions keep their queued-leg path.
                 */
                int live_move=(run || !extend) && run==steering_run && active_move && request_move_path;
                for (int index=0;live_move && index<member_count;++index) {
                    int32_t queued=0; uintptr_t action=0;
                    if (read_pointer(actors[index])!=(uintptr_t)engine+0x649328
                        || !point_is_writable(actors[index]+0x460)
                        || !pending_move(actors[index],&queued,&action)) live_move=0;
                }
                uintptr_t follower_pending[6]={0};
                if (continuing && !live_move) {
                    /* Stock shift-click appends a MoveToPoint and does not set
                     * the forced-action restart flag while action 23 is active.
                     * Keep one future leg at most: a held stick or stalled path
                     * must not accumulate an unbounded action queue.
                     */
                    for (int index=0;index<member_count;++index) {
                        uintptr_t actor=object_for_id(members[index]);
                        int32_t queued=0; uint16_t action=0;
                        if (!actor || read_pointer(actor+0x18)!=area
                            || !read_memory(actor+0x348,&queued,4) || queued<0 || queued>64
                            || !read_memory(actor+0x3f0,&action,2)) goto remaining_distance;
                        if (index==0 && queued>0) goto remaining_distance;
                        if (index>0 && queued>0) {
                            /* A slower follower must not block the leader's
                             * next leg. Replace its one obsolete future move,
                             * leaving the current move/animation untouched.
                             * Refuse unrelated or unexpected queued actions.
                             */
                            uintptr_t node=read_pointer(actor+0x338);
                            uintptr_t pending=read_pointer(node+0x10); uint16_t opcode=0;
                            if (queued!=1 || !active_move || !pending
                                || !read_memory(pending,&opcode,2) || opcode!=23) goto remaining_distance;
                            follower_pending[index]=actor;
                        }
                        if (index==0 && action!=23) continuing=0;
                    }
                }
                int lookahead=count>1 ? 300 : 220;
                steering_target[0]=origin[0]+(int32_t)(dx/length*lookahead);
                steering_target[1]=origin[1]+(int32_t)(dy/length*(lookahead*0.75));
                if (steering_target[0]>0 && steering_target[1]>0 && steering_target[0]<=32767 && steering_target[1]<=32767) {
                    uint64_t point; memcpy(&point,steering_target,8);
                    /* Stock area's ground-click path calls 0x1a0e80 before
                     * CGameGroup::Move. AlwaysRun only stores a preference;
                     * this helper applies walking/running through virtual
                     * +0x1f0. Apply once per ownership/preference change,
                     * not again at every continuation waypoint.
                     */
                    if (!same_owner || run!=steering_run) prepare_group_run((void *)area);
                    if (live_move) {
                        for (int index=0;index<member_count;++index) clear_pending_actions((void *)actors[index],0);
                    } else if (continuing) {
                        for (int index=1;index<member_count;++index) {
                            if (follower_pending[index]) {
                                clear_pending_actions((void *)follower_pending[index],0);
                                log_runtime(12,202,index,1);
                            }
                        }
                    }
                    if (!continuing && !live_move) {
                        if (active_move) {
                            /* A turn/recovery replaces future orders while the
                             * current MoveToPoint remains active. Full group
                             * ClearActions additionally installs an idle action,
                             * resetting animation before the new move starts.
                             */
                            for (int index=0;index<member_count;++index)
                                clear_pending_actions((void *)actors[index],0);
                        } else group_clear_actions((void *)(game+0xa290));
                    }
                    controller_steering_active=1;
                    group_move((void *)(game+0xa290),point,continuing || live_move,formation,UINT64_MAX);
                    controller_steering_active=0;
                    if (live_move) {
                        for (int index=0;index<member_count;++index) {
                            int32_t destination[2];
                            if (retarget_active_move(actors[index],area,destination)) {
                                if (!index) memcpy(steering_target,destination,8);
                                log_runtime(12,203,index,1);
                            }
                        }
                    }
                    log_runtime(operation,steering_target[0],steering_target[1],formation);
                    steering_area=area; steering_leader=id; steering_owned=1;
                    steering_run=run; steering_count=member_count;
                    if (member_count) memcpy(steering_members,members,member_count*4);
                    log_runtime(12,201,live_move ? 2 : continuing,run);
                    issued=1;
                }
            }
        }
remaining_distance:
        if (steering_area==area && steering_leader==id) {
            double x=(double)steering_target[0]-origin[0],y=((double)steering_target[1]-origin[1])*1.333333;
            remaining=sqrt(x*x+y*y);
        }
    }
    if (operation==11) steering_owned=0;
    push_number(state,remaining);
    if (operation==9) {push_number(state,issued); return 2;}
    return 1;
}
