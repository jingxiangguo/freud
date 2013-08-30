#include <boost/python.hpp>
#include <boost/shared_array.hpp>

#include "LinkCell.h"
#include "num_util.h"
#include "trajectory.h"

#ifndef _complement_H__
#define _complement_H__

namespace freud { namespace complement {

//! Computes the number of matches for a given set of points
/*! A given set of reference points is given around which the RDF is computed and averaged in a sea of data points.
    Computing the RDF results in an rdf array listing the value of the RDF at each given r, listed in the r array.

    The values of r to compute the rdf at are controlled by the rmax and dr parameters to the constructor. rmax
    determins the maximum r at which to compute g(r) and dr is the step size for each bin.

    <b>2D:</b><br>
    RDF properly handles 2D boxes. As with everything else in freud, 2D points must be passed in as
    3 component vectors x,y,0. Failing to set 0 in the third component will lead to undefined behavior.
*/
class complement
    {
    public:
        //! Constructor
        complement(const trajectory::Box& box, float rmax);

        //! Destructor
        ~complement();

        //! Get the simulation box
        const trajectory::Box& getBox() const
            {
            return m_box;
            }

        //! Check if a cell list should be used or not
        bool useCells();

        // Some of these should be made private...

        //! Check if a point is on the same side of a line as a reference point
        bool _sameSidePy(boost::python::numeric::array A,
                            boost::python::numeric::array B,
                            boost::python::numeric::array r,
                            boost::python::numeric::array p);

        bool sameSide(float3 A, float3 B, float3 r, float3 p);

        //! Check if point p is inside triangle t
        bool _isInsidePy(boost::python::numeric::array t,
                            boost::python::numeric::array p);

        bool isInside(float2 t[], float2 p);

        bool isInside(float3 t[], float3 p);

        void _crossPy(boost::python::numeric::array v,
                        boost::python::numeric::array v1,
                        boost::python::numeric::array v2);

        //! Take the cross product of two float3 vectors

        float3 cross(float2 v1, float2 v2);

        float3 cross(float3 v1, float3 v2);

        float _dotPy(boost::python::numeric::array v1,
                        boost::python::numeric::array v2);

        //! Take the dot product of two float3 vectors
        float dot2(float2 v1, float2 v2);

        float dot3(float3 v1, float3 v2);

        void _mat_rotPy(boost::python::numeric::array p_rot,
                        boost::python::numeric::array p,
                        float angle);

        //! Rotate a float2 point by angle angle
        float2 mat_rotate(float2 point, float angle);

        void _into_localPy(boost::python::numeric::array local,
                        boost::python::numeric::array p_ref,
                        boost::python::numeric::array p,
                        boost::python::numeric::array vert,
                        float a_ref,
                        float a);

        // Take a vertex about point point and move into the local coords of the ref point
        float2 into_local(float2 ref_point,
                            float2 point,
                            float2 vert,
                            float ref_angle,
                            float angle);

        float cavity_depth(float2 t[]);

        //! Compute the complement function
        void compute(unsigned int* match,
                float3* points,
                unsigned int* types,
                float* angles,
                float2* shapes,
                unsigned int* ref_list,
                unsigned int* check_list,
                unsigned int* ref_verts,
                unsigned int* check_verts,
                unsigned int Np,
                unsigned int Nt,
                unsigned int Nmaxverts,
                unsigned int Nref,
                unsigned int Ncheck,
                unsigned int Nmaxrefverts,
                unsigned int Nmaxcheckverts);

        //! Compute the RDF
    void computeWithoutCellList(unsigned int* match,
                float3* points,
                unsigned int* types,
                float* angles,
                float2* shapes,
                unsigned int* ref_list,
                unsigned int* check_list,
                unsigned int* ref_verts,
                unsigned int* check_verts,
                unsigned int Np,
                unsigned int Nt,
                unsigned int Nmaxverts,
                unsigned int Nref,
                unsigned int Ncheck,
                unsigned int Nmaxrefverts,
                unsigned int Nmaxcheckverts);

    //! Compute the RDF
    void computeWithCellList(unsigned int* match,
                float3* points,
                unsigned int* types,
                float* angles,
                float2* shapes,
                unsigned int* ref_list,
                unsigned int* check_list,
                unsigned int* ref_verts,
                unsigned int* check_verts,
                unsigned int Np,
                unsigned int Nt,
                unsigned int Nmaxverts,
                unsigned int Nref,
                unsigned int Ncheck,
                unsigned int Nmaxrefverts,
                unsigned int Nmaxcheckverts);

        //! Python wrapper for compute
    void computePy(boost::python::numeric::array match,
                    boost::python::numeric::array points,
                    boost::python::numeric::array types,
                    boost::python::numeric::array angles,
                    boost::python::numeric::array shapes,
                    boost::python::numeric::array ref_list,
                    boost::python::numeric::array check_list,
                    boost::python::numeric::array ref_verts,
                    boost::python::numeric::array check_verts);

        unsigned int getNpairPy()
            {
            return m_nmatch;
            }

    private:
        trajectory::Box m_box;            //!< Simulation box the particles belong in
        float m_rmax;                     //!< Maximum r at which to compute g(r)
        float m_dr;                       //!< Step size for r in the computation
        locality::LinkCell* m_lc;       //!< LinkCell to bin particles for the computation
        unsigned int m_nmatch;             //!< Number of matches
        unsigned int m_nP;                  //!< Number of particles

    };

/*! \internal
    \brief Exports all classes in this file to python
*/
void export_complement();

}; }; // end namespace freud::complement

#endif // _complement_H__
