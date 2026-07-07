from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
import csv
import io
from decimal import Decimal
from datetime import datetime

from .models import Medicine
from .serializers import MedicineSerializer
from apps.audit.permissions import IsAdminOrSuperAdmin
from utils.publisher import publish_event
from utils.throttling import GlobalUserThrottle, BurstThrottle, WriteThrottle
from utils.error import ErrorHandler


class MedicineListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

    def get(self, request):
        try:
            medicines = Medicine.objects.all().order_by("-created_at")
            return Response(MedicineSerializer(medicines, many=True).data)
        except Exception as exc:
            return Response({"message": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        try:
            serializer = MedicineSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            medicine = serializer.save()
            publish_event("pharmtrack.medicine", "medicine.created", {
                "event": "medicine.created",
                "medicine_id": str(medicine.id),
                "name": medicine.name,
                "quantity": medicine.quantity,
                "batch": medicine.batch,
                "expiry_date": str(medicine.expiry_date),
                "price": str(medicine.price),
            })
            return Response(MedicineSerializer(medicine).data,
                            status=status.HTTP_201_CREATED)
        except Exception as exc:
            return ErrorHandler.handle(exc, "Failed to create medicine")


class MedicineDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

    def get_object(self, pk):
        try:
            return Medicine.objects.get(pk=pk)
        except Medicine.DoesNotExist:
            return None

    def get(self, request, pk):
        try:
            med = self.get_object(pk)
            if not med:
                return Response({"message": "Not found"},
                                status=status.HTTP_404_NOT_FOUND)
            return Response(MedicineSerializer(med).data)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return Response({"message": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        try:
            med = self.get_object(pk)
            if not med:
                return Response({"message": "Not found"},
                                status=status.HTTP_404_NOT_FOUND)
            serializer = MedicineSerializer(
                med, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(MedicineSerializer(med).data)
        except Exception as exc:
            return Response({"message": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            med = self.get_object(pk)
            if not med:
                return Response({"message": "Not found"},
                                status=status.HTTP_404_NOT_FOUND)
            med.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            return Response({"message": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)


class MedicineBulkUploadView(APIView):
    """
    POST /medicines/bulk-upload/

    Accepts CSV file with the following columns:
    - name (required)
    - batch (required)
    - expiry_date (required, format: YYYY-MM-DD)
    - quantity (required, integer)
    - price (required, decimal)
    - qr_code (optional)

    Returns detailed response with success/failure counts and error details.

    """
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

    def post(self, request):
        try:

            # Check if file is provided
            if 'file' not in request.FILES:
                return Response(
                    {"message": "No file provided", "success": False},
                    status=status.HTTP_400_BAD_REQUEST
                )

            csv_file = request.FILES['file']

            # Validate file type
            if not csv_file.name.endswith('.csv'):
                return Response(
                    {"message": "File must be CSV format", "success": False},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Decode CSV file
            try:
                file_content = csv_file.read().decode('utf-8')
            except UnicodeDecodeError:
                return Response(
                    {"message": "Invalid CSV encoding. Please use UTF-8",
                        "success": False},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Parse CSV
            csv_reader = csv.DictReader(io.StringIO(file_content))

            if not csv_reader.fieldnames:
                return Response(
                    {"message": "CSV file is empty", "success": False},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate required fields
            required_fields = {
                'name',
                'batch',
                'expiry_date',
                'quantity',
                'price'}
            if not required_fields.issubset(set(csv_reader.fieldnames)):
                return Response(
                    {
                        "message": f"CSV must contain these columns: {', '.join(required_fields)}",
                        "success": False
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Process rows and collect errors
            medicines_to_create = []
            errors = []
            row_number = 2  # Start at 2 because row 1 is header

            for row in csv_reader:
                try:
                    # Validate and convert data
                    name = row.get('name', '').strip()
                    batch = row.get('batch', '').strip()
                    expiry_date_str = row.get('expiry_date', '').strip()
                    quantity_str = row.get('quantity', '').strip()
                    price_str = row.get('price', '').strip()
                    qr_code = row.get('qr_code', '').strip() or None

                    # Validate required fields
                    if not name:
                        errors.append(f"Row {row_number}: name is required")
                        row_number += 1
                        continue

                    if not batch:
                        errors.append(f"Row {row_number}: batch is required")
                        row_number += 1
                        continue

                    if not expiry_date_str:
                        errors.append(
                            f"Row {row_number}: expiry_date is required")
                        row_number += 1
                        continue

                    if not quantity_str:
                        errors.append(
                            f"Row {row_number}: quantity is required")
                        row_number += 1
                        continue

                    if not price_str:
                        errors.append(f"Row {row_number}: price is required")
                        row_number += 1
                        continue

                    # Parse expiry_date
                    try:
                        expiry_date = datetime.strptime(
                            expiry_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(
                            f"Row {row_number}: expiry_date must be in YYYY-MM-DD format")
                        row_number += 1
                        continue

                    # Parse quantity
                    try:
                        quantity = int(quantity_str)
                        if quantity < 0:
                            raise ValueError("Quantity must be non-negative")
                    except ValueError as e:
                        errors.append(
                            f"Row {row_number}: quantity must be a valid integer ({
                                str(e)})")
                        row_number += 1
                        continue

                    # Parse price
                    try:
                        price = Decimal(price_str)
                        if price < 0:
                            raise ValueError("Price must be non-negative")
                    except Exception:
                        errors.append(
                            f"Row {row_number}: price must be a valid decimal number")
                        row_number += 1
                        continue

                    # Create medicine object
                    medicine = Medicine(
                        name=name,
                        batch=batch,
                        expiry_date=expiry_date,
                        quantity=quantity,
                        price=price,
                        qr_code=qr_code
                    )
                    medicines_to_create.append(medicine)

                except Exception as e:
                    errors.append(f"Row {row_number}: {str(e)}")

                row_number += 1

            # If no valid rows, return error
            if not medicines_to_create:
                return Response(
                    {
                        "success": False,
                        "message": "No valid records found in CSV",
                        "total_rows": row_number - 2,
                        "errors": errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Bulk create medicines in a transaction
            with transaction.atomic():
                created_medicines = Medicine.objects.bulk_create(
                    medicines_to_create)

                # Publish events for each created medicine
                for medicine in created_medicines:
                    try:
                        publish_event("pharmtrack.medicine", "medicine.created", {
                            "event": "medicine.created",
                            "medicine_id": str(medicine.id),
                            "name": medicine.name,
                            "quantity": medicine.quantity,
                            "batch": medicine.batch,
                            "expiry_date": str(medicine.expiry_date),
                            "price": str(medicine.price),
                        })
                    except Exception as e:
                        # Log but don't fail the upload
                        print(
                            f"Failed to publish event for medicine {
                                medicine.id}: {
                                str(e)}")

            return Response(
                {
                    "success": True,
                    "message": f"Successfully uploaded {len(created_medicines)} medicines",
                    "total_rows": row_number - 2,
                    "created": len(created_medicines),
                    "failed": len(errors),
                    "errors": errors if errors else None,
                    "medicines": MedicineSerializer(created_medicines, many=True).data
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as exc:
            return ErrorHandler.handle(exc, "Bulk upload failed")
