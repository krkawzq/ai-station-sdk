from __future__ import annotations

import json

from aistation.modeling import Image, JobVolume, Node, Pod, Port, ResourceGroup, Task, User, WorkPlatform


def make_user(
    *,
    account: str = "alice",
    group_id: str = "project-1",
    token: str = "token-1",
) -> User:
    return User(
        user_id="user-1",
        account=account,
        user_name=account.title(),
        group_id=group_id,
        role_type=2,
        user_type=0,
        token=token,
        is_first_login=False,
    )


def make_node(
    *,
    node_name: str = "gpu-node-1",
    group_id: str = "group-1",
    group_name: str = "GPU-POOL-A",
    card_type: str = "Synthetic-A100-80GB",
    cards_total: int = 8,
    cards_used: int = 2,
) -> Node:
    return Node(
        node_id=f"{node_name}-id",
        node_name=node_name,
        node_ip="198.51.100.10",
        group_id=group_id,
        group_name=group_name,
        card_type=card_type,
        card_kind="GPU",
        card_memory_gb=80,
        cards_total=cards_total,
        cards_used=cards_used,
        cpu=128,
        cpu_used=16,
        memory_gb=512,
        disk_gb=2048,
        switch_type="ib",
        status="ready",
        resource_status="healthy",
        role="node",
        task_count=1,
        task_users=["user-a"],
        is_mig=False,
    )


def make_group(
    *,
    group_id: str = "group-1",
    group_name: str = "GPU-POOL-A",
    card_type: str = "Synthetic-A100-80GB",
    card_kind: str = "GPU",
    switch_type: str = "ib",
    total_cards: int = 8,
    used_cards: int = 2,
) -> ResourceGroup:
    return ResourceGroup(
        group_id=group_id,
        group_name=group_name,
        card_type=card_type,
        card_kind=card_kind,
        switch_type=switch_type,
        node_count=1,
        total_cards=total_cards,
        used_cards=used_cards,
        total_cpu=128,
        total_memory_gb=512,
        node_names=["gpu-node-1"],
    )


def make_image(
    *,
    name: str = "registry.example.invalid/ml/pytorch",
    tag: str = "latest",
    image_type: str = "pytorch",
    share: int = 2,
    pull_count: int = 100,
    owner: str = "system-user",
) -> Image:
    return Image(
        id=f"{name}:{tag}",
        name=name,
        tag=tag,
        image_type=image_type,
        share=share,
        size_bytes=1024,
        pull_count=pull_count,
        owner=owner,
        make_type=0,
        logo_id=None,
        create_time="2026-01-01 00:00:00",
        update_time="2026-01-02 00:00:00",
    )


def make_job_volume(volume_mount: str = "/workspace") -> JobVolume:
    return JobVolume(
        file_model=2,
        function_model=2,
        volume_mount=volume_mount,
        storage_name="master",
        bucket="",
    )


def make_task(
    *,
    task_id: str = "task-1",
    name: str = "TaskOne",
    status: str = "Pending",
    command: str = "sleep 30",
    image: str = "registry.example.invalid/ml/pytorch:latest",
    image_type: str = "pytorch",
    resource_group_id: str = "group-1",
    resource_group_name: str = "GPU-POOL-A",
    ports: str = "",
    dist_flag: bool = False,
    mpi_flag: bool = False,
) -> Task:
    return Task(
        id=task_id,
        name=name,
        status=status,
        user_id="user-1",
        user_name="Alice",
        project_id="project-1",
        project_name="Project One",
        resource_group_id=resource_group_id,
        resource_group_name=resource_group_name,
        job_type=image_type,
        image=image,
        image_type=image_type,
        image_flag=0,
        command=command,
        start_script="",
        exec_dir="",
        mount_dir="/workspace",
        script_dir="/workspace",
        log_out="/workspace/logs",
        log_persistence="master",
        config=json.dumps(
            {
                "worker": {
                    "nodeNum": 1,
                    "cpuNum": 4,
                    "acceleratorCardNum": 1 if image_type != "other" else 0,
                    "memory": 16,
                    "minNodeNum": -1,
                }
            }
        ),
        gpu_info="{}",
        pod_info="{}",
        switch_type="ib",
        dist_flag=dist_flag,
        mpi_flag=mpi_flag,
        is_elastic=False,
        shm_size=4,
        ports=ports,
        emergency_flag=False,
        task_type=1,
        task_type_name="训练任务",
        create_time_ms=1,
        start_time_ms=2,
        end_time_ms=None,
        run_time_s=3,
        node_name="gpu-node-1",
        job_volume=[make_job_volume()],
        status_reason="",
    )


def make_pod(*, node_ip: str = "198.51.100.10", node_port: int = 30080) -> Pod:
    return Pod(
        pod_id="pod-1",
        pod_name="pod-one",
        pod_name_changed="pod-one-display",
        pod_status="Running",
        node_name="gpu-node-1",
        node_ip=node_ip,
        pod_ip="203.0.113.10",
        gpu_ids="GPU-1",
        gpu_names="gpu-node-1_0",
        pod_gpu_type="Synthetic-A100-80GB",
        ports=[Port(port=8080, target_port=8080, node_port=node_port)],
        restart_count=0,
        switch_type="IB",
        create_time_ms=1,
    )


def make_workplatform(
    *,
    wp_id: str = "wp-1",
    name: str = "DevBoxOne",
    status: str = "Running",
    group_id: str = "group-dev",
    group_name: str = "DEV-POOL",
) -> WorkPlatform:
    return WorkPlatform(
        wp_id=wp_id,
        wp_name=name,
        wp_status=status,
        group_id=group_id,
        group_name=group_name,
        image="registry.example.invalid/ml/dev:latest",
        image_type="INNER_IMAGE",
        frame_work="other",
        cpu=4,
        memory_gb=16,
        cards=0,
        card_kind="CPU",
        card_type="",
        card_memory_gb=0,
        shm_size=1,
        command="sleep infinity",
        pod_num=1,
        user_id="user-1",
        create_time="2026-01-01 00:00:00",
        env=[{"name": "MODE", "value": "dev"}],
        models=[],
        volumes=[],
    )
